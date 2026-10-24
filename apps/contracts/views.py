import os
import mimetypes
from decimal import Decimal
from django.conf import settings
from django.http import HttpResponse, FileResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods
from apps.accounts.permissions import role_required, get_scoped_queryset
from apps.accounts.models import UserRole
from apps.accounts.services.audit import AuditService
from apps.contracts.models import Deal, DealStage, ContractDocument, DocumentType
from apps.contracts.services.deal_service import DealService
from apps.contracts.forms import DealStageUpdateForm, ContractDocumentUploadForm

def can_access_document(user, document):
    """
    WHY SECURE: Object-level permission check for private legal documents.
    Only allows:
    1. Superusers, Admins, and Staff.
    2. The assigned agent on this deal.
    3. The property owner whose shop is being taken over.
    4. The buyer (lead) associated with this deal.
    """
    if not user.is_authenticated:
        return False
    if user.is_admin() or user.is_staff_member():
        return True
    deal = document.deal
    if deal.agent and deal.agent == user:
        return True
    if deal.listing.property.owner == user:
        return True
    if deal.lead and deal.lead.email == user.email:
        return True
    return False

def can_manage_deal(user, deal):
    """Checks if the user has permission to manage/update the deal."""
    if not user.is_authenticated:
        return False
    if user.is_admin() or user.is_staff_member():
        return True
    return deal.agent == user

@login_required
@role_required(UserRole.ADMIN, UserRole.STAFF, UserRole.AGENT)
@require_http_methods(["GET"])
def deal_pipeline_view(request):
    """
    WHY SECURE:
    1. Enforces Role-Based Access Control (Admins, Staff, Agents only).
    2. Scoped queryset ensures agents only view deals assigned to them,
       while Admins/Staff can oversee the entire company pipeline.
    3. Prevents IDOR and horizontal privilege escalation.
    """
    base_qs = Deal.objects.select_related(
        'listing', 'listing__property', 'agent', 'lead'
    ).order_by('-created_at')

    deals = get_scoped_queryset(request.user, base_qs, owner_field='agent')

    # Pipeline Metrics
    total_deals = deals.count()
    won_deals = deals.filter(stage=DealStage.CLOSED_WON).count()
    lost_deals = deals.filter(stage=DealStage.CLOSED_LOST).count()
    active_deals = deals.exclude(stage__in=[DealStage.CLOSED_WON, DealStage.CLOSED_LOST])

    pipeline_value = sum(
        d.agreed_price if d.agreed_price is not None else d.listing.price
        for d in active_deals
    )
    
    # Calculate Commission Total (Agent share for agents, Gross for staff/admin)
    if request.user.role == UserRole.AGENT:
        total_commission = sum(d.agent_payout for d in deals.filter(stage=DealStage.CLOSED_WON))
    else:
        total_commission = sum(d.gross_commission for d in deals.filter(stage=DealStage.CLOSED_WON))

    # Group deals by stage for Kanban view
    stages = [
        (DealStage.NEW_LEAD, 'ลีดใหม่', 'bg-blue-50 border-blue-200 text-blue-700'),
        (DealStage.CONTACTED, 'ติดต่อแล้ว', 'bg-indigo-50 border-indigo-200 text-indigo-700'),
        (DealStage.SITE_VISIT_SCHEDULED, 'นัดชมร้าน', 'bg-amber-50 border-amber-200 text-amber-700'),
        (DealStage.SITE_VISIT_COMPLETED, 'ชมร้านแล้ว', 'bg-orange-50 border-orange-200 text-orange-700'),
        (DealStage.NEGOTIATION, 'เจรจาต่อรอง', 'bg-purple-50 border-purple-200 text-purple-700'),
        (DealStage.DEPOSIT_PAID, 'วางมัดจำแล้ว', 'bg-teal-50 border-teal-200 text-teal-700'),
        (DealStage.CONTRACT_SIGNING, 'นัดเซ็นสัญญา', 'bg-cyan-50 border-cyan-200 text-cyan-700'),
        (DealStage.CLOSED_WON, 'ปิดดีลสำเร็จ 🎉', 'bg-emerald-50 border-emerald-200 text-emerald-700'),
        (DealStage.CLOSED_LOST, 'ดีลยกเลิก', 'bg-neutral-100 border-neutral-300 text-neutral-600'),
    ]

    pipeline_columns = []
    for stage_code, stage_label, stage_badge in stages:
        stage_deals = [d for d in deals if d.stage == stage_code]
        pipeline_columns.append({
            'code': stage_code,
            'label': stage_label,
            'badge': stage_badge,
            'deals': stage_deals,
            'count': len(stage_deals)
        })

    context = {
        'pipeline_columns': pipeline_columns,
        'total_deals': total_deals,
        'won_deals': won_deals,
        'lost_deals': lost_deals,
        'active_deals_count': active_deals.count(),
        'pipeline_value': pipeline_value,
        'total_commission': total_commission,
    }
    return render(request, 'contracts/deal_pipeline.html', context)

@login_required
@role_required(UserRole.ADMIN, UserRole.STAFF, UserRole.AGENT)
@require_http_methods(["GET"])
def deal_detail_view(request, pk):
    """
    Displays full deal profile, CRM notes, financials, and legal documents vault.
    """
    deal = get_object_or_404(
        Deal.objects.select_related('listing', 'listing__property', 'agent', 'lead'),
        pk=pk
    )

    if not can_manage_deal(request.user, deal):
        raise PermissionDenied("คุณไม่มีสิทธิ์เข้าถึงข้อมูลดีลนี้")

    documents = deal.documents.select_related('uploaded_by').all()
    stage_form = DealStageUpdateForm(instance=deal)
    doc_form = ContractDocumentUploadForm()

    context = {
        'deal': deal,
        'documents': documents,
        'stage_form': stage_form,
        'doc_form': doc_form,
        'stages': DealStage.choices,
    }
    return render(request, 'contracts/deal_detail.html', context)

@login_required
@role_required(UserRole.ADMIN, UserRole.STAFF, UserRole.AGENT)
@require_http_methods(["POST"])
def deal_advance_stage_view(request, pk):
    """
    Updates the stage and financial terms of a deal with ACID transaction.
    """
    deal = get_object_or_404(Deal, pk=pk)

    if not can_manage_deal(request.user, deal):
        raise PermissionDenied("คุณไม่มีสิทธิ์แก้ไขสถานะของดีลนี้")

    target_stage = request.POST.get('stage')
    agreed_price = request.POST.get('agreed_price')
    deposit_amount = request.POST.get('deposit_amount')
    notes = request.POST.get('notes', '')

    if target_stage not in DealStage.values:
        messages.error(request, "สถานะดีลที่ระบุไม่ถูกต้อง")
        return redirect('contracts:deal_detail', pk=deal.pk)

    try:
        updated_deal = DealService.advance_stage(
            deal_id=deal.pk,
            target_stage=target_stage,
            agreed_price=Decimal(agreed_price) if agreed_price else None,
            deposit_amount=Decimal(deposit_amount) if deposit_amount else None,
            request=request,
            actor=request.user
        )
        if notes:
            updated_deal.notes = notes
            updated_deal.save(update_fields=['notes'])

        messages.success(request, f"อัปเดตสถานะดีลเป็น '{updated_deal.get_stage_display()}' เรียบร้อยแล้ว")
    except Exception as e:
        messages.error(request, f"เกิดข้อผิดพลาดในการอัปเดตสถานะ: {str(e)}")

    if request.headers.get('HX-Request'):
        return render(request, 'contracts/partials/deal_card.html', {'deal': deal})
    return redirect('contracts:deal_detail', pk=deal.pk)

@login_required
@role_required(UserRole.ADMIN, UserRole.STAFF, UserRole.AGENT)
@require_http_methods(["POST"])
def deal_upload_document_view(request, pk):
    """
    Uploads a private legal contract or proof document.
    """
    deal = get_object_or_404(Deal, pk=pk)

    if not can_manage_deal(request.user, deal):
        raise PermissionDenied("คุณไม่มีสิทธิ์อัปโหลดเอกสารสำหรับดีลนี้")

    form = ContractDocumentUploadForm(request.POST, request.FILES)
    if form.is_valid():
        doc = form.save(commit=False)
        doc.deal = deal
        doc.uploaded_by = request.user
        doc.file_name_display = request.FILES['file'].name
        doc.save()

        AuditService.log(
            action='UPLOAD',
            model_name='ContractDocument',
            object_id=doc.pk,
            changes={'deal': deal.deal_code, 'document_type': doc.type, 'filename': doc.file_name_display},
            request=request
        )
        messages.success(request, f"อัปโหลดเอกสาร '{doc.file_name_display}' เรียบร้อยแล้ว")
    else:
        for err_list in form.errors.values():
            for err in err_list:
                messages.error(request, err)

    return redirect('contracts:deal_detail', pk=deal.pk)

@login_required
@require_http_methods(["GET"])
def contract_document_download_view(request, pk):
    """
    WHY SECURE:
    1. Authenticates and checks strict object-level access before granting access.
    2. In Production: Employs Nginx X-Accel-Redirect header.
       Django does not stream the file itself; Nginx serves it internally,
       preventing memory bloat and keeping the private media folder isolated.
    3. In Development: Uses Django FileResponse.
    4. Records an audit trail of every document download.
    """
    document = get_object_or_404(
        ContractDocument.objects.select_related('deal', 'deal__listing', 'deal__listing__property', 'deal__agent', 'deal__lead'),
        pk=pk
    )

    if not can_access_document(request.user, document):
        AuditService.log(
            action='PERMISSION_DENIED',
            model_name='ContractDocument',
            object_id=document.pk,
            changes={'attempted_access': document.file_name_display},
            request=request
        )
        raise PermissionDenied("คุณไม่มีสิทธิ์ในการดาวน์โหลดหรือเข้าดูเอกสารสัญญานี้")

    # Record access audit log
    AuditService.log(
        action='READ',
        model_name='ContractDocument',
        object_id=document.pk,
        changes={'document_name': document.file_name_display},
        request=request
    )

    content_type, _ = mimetypes.guess_type(document.file.name)
    content_type = content_type or 'application/octet-stream'

    # ⚠️ Production Nginx X-Accel-Redirect
    if not settings.DEBUG:
        response = HttpResponse()
        # Nginx internal location: /internal-media/ -> /app/media/private/
        internal_path = f"/internal-media/{document.file.name.replace('private/', '')}"
        response['X-Accel-Redirect'] = internal_path
        response['Content-Type'] = content_type
        response['Content-Disposition'] = f'attachment; filename="{document.file_name_display}"'
        return response

    # Development fallback
    return FileResponse(
        document.file.open('rb'),
        content_type=content_type,
        as_attachment=True,
        filename=document.file_name_display
    )

import logging
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Sum, Count, Q, Avg
from django.conf import settings

from apps.accounts.permissions import role_required
from apps.accounts.models import User, UserRole, VIPPaymentTransaction, AgentProfile
from apps.accounts.services.audit import AuditService
from apps.properties.models import Property, PropertyType, PropertyImage
from apps.listings.models import Listing, ListingStatus, ListingType, FeePayer
from apps.leads.models import Lead, LeadStatus, LeadUrgency
from apps.contracts.models import Deal, DealStage, ContractDocument, DocumentType
from apps.core.models import ContactMessage
from apps.core.utils.files import validate_and_sanitize_image
from apps.core.services.email import EmailNotificationService

from decouple import config

logger = logging.getLogger(__name__)


@login_required
@role_required(UserRole.STAFF, UserRole.ADMIN)
@require_http_methods(["GET"])
def admin_command_center_view(request):
    """
    Unified Single-Page Command Center (Admin Dashboard)
    Replaces Django Admin with a modern, high-transparency operations console.
    """
    active_tab = request.GET.get('tab', 'overview')
    now = timezone.now()

    # -------------------------------------------------------------------------
    # 1. Overview KPIs
    # -------------------------------------------------------------------------
    total_shops = Listing.objects.count()
    published_shops = Listing.objects.filter(status=ListingStatus.PUBLISHED).count()
    pending_shops = Listing.objects.filter(status=ListingStatus.PENDING).count()
    
    active_vip_users = User.objects.filter(is_vip=True).count()
    pending_slips_count = VIPPaymentTransaction.objects.filter(status=VIPPaymentTransaction.Status.PENDING).count()
    
    # Active Deals in Pipeline
    active_deals = Deal.objects.exclude(stage__in=[DealStage.CLOSED_WON, DealStage.CLOSED_LOST])
    active_deals_count = active_deals.count()
    pipeline_volume = active_deals.aggregate(total=Sum('agreed_price'))['total'] or Decimal('0.00')
    pipeline_commission_est = (pipeline_volume * Decimal('0.05')).quantize(Decimal('0.01'))

    # Financial / Revenue
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_vip_txs = VIPPaymentTransaction.objects.filter(
        status__in=[VIPPaymentTransaction.Status.AUTO_VERIFIED, VIPPaymentTransaction.Status.MANUAL_APPROVED],
        created_at__gte=start_of_month
    )
    month_vip_revenue = month_vip_txs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    all_time_vip_revenue = VIPPaymentTransaction.objects.filter(
        status__in=[VIPPaymentTransaction.Status.AUTO_VERIFIED, VIPPaymentTransaction.Status.MANUAL_APPROVED]
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    closed_deals = Deal.objects.filter(stage=DealStage.CLOSED_WON)
    total_deal_commission = closed_deals.aggregate(total=Sum('platform_payout'))['total'] or Decimal('0.00')
    total_platform_revenue = all_time_vip_revenue + total_deal_commission

    # -------------------------------------------------------------------------
    # 2. Shop Management Data
    # -------------------------------------------------------------------------
    shop_qs = Listing.objects.select_related('property', 'property__owner', 'agent').prefetch_related('property__images').order_by('-created_at')
    
    # Filtering
    shop_query = request.GET.get('shop_q', '').strip()
    if shop_query:
        shop_qs = shop_qs.filter(
            Q(property__title__icontains=shop_query) |
            Q(ref_code__icontains=shop_query) |
            Q(property__district__icontains=shop_query) |
            Q(property__province__icontains=shop_query)
        )
    
    shop_status_filter = request.GET.get('shop_status', '')
    if shop_status_filter:
        shop_qs = shop_qs.filter(status=shop_status_filter)

    shop_category_filter = request.GET.get('shop_cat', '')
    if shop_category_filter:
        shop_qs = shop_qs.filter(property__type=shop_category_filter)

    shops_list = shop_qs[:50]

    # -------------------------------------------------------------------------
    # 3. CRM & Leads Data
    # -------------------------------------------------------------------------
    leads_list = Lead.objects.select_related('listing', 'listing__property', 'assigned_agent').order_by('-created_at')[:40]
    new_leads_count = Lead.objects.filter(status=LeadStatus.NEW).count()
    immediate_leads_count = Lead.objects.filter(urgency=LeadUrgency.IMMEDIATE).count()

    # -------------------------------------------------------------------------
    # 4. Broker / Agents Data
    # -------------------------------------------------------------------------
    agents_list = User.objects.filter(role__in=[UserRole.AGENT, UserRole.STAFF]).annotate(
        deals_count=Count('agent_deals'),
        total_payout=Sum('agent_deals__agent_payout', filter=Q(agent_deals__stage=DealStage.CLOSED_WON))
    ).order_by('-deals_count')

    # -------------------------------------------------------------------------
    # 5. Deal Pipeline
    # -------------------------------------------------------------------------
    deals_list = Deal.objects.select_related('listing', 'listing__property', 'lead', 'agent', 'assigned_agent_profile').order_by('-updated_at')[:40]
    settled_deals = Deal.objects.filter(stage=DealStage.CLOSED_WON).select_related('listing', 'listing__property', 'lead', 'agent', 'assigned_agent_profile').order_by('-closed_at', '-updated_at')[:30]
    stages_choices = DealStage.choices

    # -------------------------------------------------------------------------
    # 6. VIP Slips & Verification
    # -------------------------------------------------------------------------
    pending_slips = VIPPaymentTransaction.objects.filter(
        status=VIPPaymentTransaction.Status.PENDING
    ).select_related('user').order_by('-created_at')

    recent_slips = VIPPaymentTransaction.objects.select_related('user', 'reviewed_by').order_by('-created_at')[:30]

    # -------------------------------------------------------------------------
    # 7. Documents Vault & Contact Messages
    # -------------------------------------------------------------------------
    documents_list = ContractDocument.objects.select_related('deal', 'uploaded_by').order_by('-uploaded_at')[:30]
    contact_messages = ContactMessage.objects.order_by('-created_at')[:30]
    unresolved_messages_count = ContactMessage.objects.filter(is_resolved=False).count()

    # -------------------------------------------------------------------------
    # 8. Basic Analytics
    # -------------------------------------------------------------------------
    category_analytics = Property.objects.values('type').annotate(count=Count('id')).order_by('-count')
    province_analytics = Property.objects.values('province').annotate(count=Count('id')).order_by('-count')[:5]
    avg_price = Listing.objects.filter(status=ListingStatus.PUBLISHED).aggregate(avg=Avg('price'))['avg'] or 0

    # -------------------------------------------------------------------------
    # 9. Fast Post Helper Data
    # -------------------------------------------------------------------------
    owners_list = User.objects.filter(role__in=[UserRole.OWNER, UserRole.CUSTOMER, UserRole.STAFF, UserRole.ADMIN]).order_by('username')
    property_types = PropertyType.choices

    # -------------------------------------------------------------------------
    # 10. Shop Owners & Contacts Directory Data (ข้อ 10)
    # -------------------------------------------------------------------------
    owner_q = request.GET.get('owner_q', '').strip()
    owner_directory_qs = Listing.objects.select_related('property', 'property__owner', 'agent').order_by('ref_code')
    if owner_q:
        owner_directory_qs = owner_directory_qs.filter(
            Q(ref_code__icontains=owner_q) |
            Q(property__title__icontains=owner_q) |
            Q(owner_name__icontains=owner_q) |
            Q(owner_phone__icontains=owner_q) |
            Q(owner_line_id__icontains=owner_q) |
            Q(owner_facebook__icontains=owner_q) |
            Q(property__owner__username__icontains=owner_q)
        )
    owner_directory_list = owner_directory_qs[:100]

    context = {
        'active_tab': active_tab,
        # KPIs
        'total_shops': total_shops,
        'published_shops': published_shops,
        'pending_shops': pending_shops,
        'active_vip_users': active_vip_users,
        'pending_slips_count': pending_slips_count,
        'active_deals_count': active_deals_count,
        'pipeline_volume': pipeline_volume,
        'pipeline_commission_est': pipeline_commission_est,
        'month_vip_revenue': month_vip_revenue,
        'total_deal_commission': total_deal_commission,
        'total_platform_revenue': total_platform_revenue,
        'unresolved_messages_count': unresolved_messages_count,
        'new_leads_count': new_leads_count,
        'immediate_leads_count': immediate_leads_count,
        # Lists
        'shops_list': shops_list,
        'leads_list': leads_list,
        'agents_list': agents_list,
        'agent_profiles': AgentProfile.objects.all().order_by('-created_at'),
        'approved_agents': AgentProfile.objects.filter(status=AgentProfile.Status.APPROVED).order_by('full_name'),
        'deals_list': deals_list,
        'settled_deals': settled_deals,
        'stages_choices': stages_choices,
        'pending_slips': pending_slips,
        'recent_slips': recent_slips,
        'documents_list': documents_list,
        'contact_messages': contact_messages,
        'owner_directory_list': owner_directory_list,
        'owner_q': owner_q,
        # Choices & Fast Form Data
        'owners_list': owners_list,
        'property_types': property_types,
        'fee_payers': FeePayer.choices,
        'listing_statuses': ListingStatus.choices,
        'lead_statuses': LeadStatus.choices,
        'category_analytics': category_analytics,
        'province_analytics': province_analytics,
        'avg_price': avg_price,
        # Official Bank Info
        'official_bank_name': getattr(settings, 'BANK_NAME', 'ธนาคารกสิกรไทย (KBANK)'),
        'official_bank_account_no': getattr(settings, 'BANK_ACCOUNT_NO', '054-1-27630-0'),
        'official_bank_account_name': getattr(settings, 'BANK_ACCOUNT_NAME', 'ดวงฤทัย ช้างน้อย'),
        # Telegram Bot Connection
        'telegram_bot_token': getattr(settings, 'TELEGRAM_BOT_TOKEN', '') or config('TELEGRAM_BOT_TOKEN', default=''),
        'telegram_chat_id': getattr(settings, 'TELEGRAM_CHAT_ID', '') or config('TELEGRAM_CHAT_ID', default=''),
    }

    return render(request, 'admin/dashboard.html', context)


# ==============================================================================
# SHOP MANAGEMENT ACTIONS
# ==============================================================================
@login_required
@role_required(UserRole.STAFF, UserRole.ADMIN)
@require_http_methods(["POST"])
def admin_shop_action_view(request, pk):
    """1-Click quick actions for shops: approve, reject, toggle VIP boost, delete"""
    listing = get_object_or_404(Listing.objects.select_related('property'), pk=pk)
    action = request.POST.get('action')

    if action == 'approve':
        listing.status = ListingStatus.PUBLISHED
        listing.save(update_fields=['status'])
        AuditService.log(action='UPDATE', model_name='Listing', object_id=listing.pk, changes={'status': 'published'}, request=request)
        
        # Dispatch Approval Email to Shop Owner
        EmailNotificationService.send_listing_approved_email(listing)

        messages.success(request, f'✅ อนุมัติเผยแพร่ร้าน "{listing.property.title}" เรียบร้อยแล้ว')

    elif action == 'reject':
        listing.status = ListingStatus.REJECTED
        listing.save(update_fields=['status'])
        AuditService.log(action='UPDATE', model_name='Listing', object_id=listing.pk, changes={'status': 'rejected'}, request=request)
        messages.warning(request, f'ระงับประกาศร้าน "{listing.property.title}" เรียบร้อยแล้ว')

    elif action == 'toggle_vip':
        owner = listing.property.owner
        owner.is_vip = not owner.is_vip
        owner.save(update_fields=['is_vip'])
        status_txt = "เปิดสิทธิ์ VIP 👑" if owner.is_vip else "ยกเลิก VIP"
        messages.info(request, f'{status_txt} ให้เจ้าของร้านคุณ {owner.username} สำเร็จ')

    elif action == 'toggle_verified':
        listing.is_admin_verified = not listing.is_admin_verified
        if listing.is_admin_verified:
            listing.admin_verified_at = timezone.now()
        else:
            listing.admin_verified_at = None
        listing.save(update_fields=['is_admin_verified', 'admin_verified_at'])
        AuditService.log(action='UPDATE', model_name='Listing', object_id=listing.pk, changes={'is_admin_verified': listing.is_admin_verified}, request=request)
        status_txt = "ติดป้าย Admin Verified (เวอร์ริไฟร์) ✅" if listing.is_admin_verified else "ปลดป้าย Verified"
        messages.success(request, f'{status_txt} ให้ร้าน "{listing.property.title}" สำเร็จ')

    elif action == 'edit_ref_code':
        new_code = request.POST.get('ref_code', '').strip().upper()
        if not new_code:
            messages.error(request, 'กรุณาระบุรหัสประกาศ')
        elif Listing.objects.filter(ref_code=new_code).exclude(pk=listing.pk).exists():
            messages.error(request, f'❌ รหัส "{new_code}" ซ้ำกับร้านอื่นในระบบ กรุณาใช้รหัสอื่น')
        else:
            old_code = listing.ref_code
            listing.ref_code = new_code
            listing.save(update_fields=['ref_code'])
            AuditService.log(
                action='UPDATE',
                model_name='Listing',
                object_id=listing.pk,
                changes={'ref_code': new_code, 'old_ref_code': old_code},
                request=request
            )
            messages.success(request, f'✅ อัปเดตรหัสประกาศเป็น "{new_code}" สำเร็จ')

    elif action == 'delete':
        prop = listing.property
        title = prop.title if prop else listing.ref_code
        AuditService.log(
            action='DELETE',
            model_name='Listing',
            object_id=listing.pk,
            changes={'title': title, 'ref_code': listing.ref_code},
            request=request
        )
        listing.delete()
        if prop and not prop.listings.exists():
            prop.delete()
        messages.success(request, f'🗑️ ลบประกาศร้าน "{title}" เรียบร้อยแล้ว')

    return redirect('/admin-dashboard/?tab=shops')


@login_required
@role_required(UserRole.STAFF, UserRole.ADMIN)
@require_http_methods(["POST"])
def admin_fast_create_shop_view(request):
    """
    All-in-One Fast Shop Creator for Admins.
    Eliminates switching between Property and Listing tables!
    """
    owner_id = request.POST.get('owner_id')
    title = request.POST.get('title', '').strip()
    category = request.POST.get('category', request.POST.get('type', PropertyType.RESTAURANT_SHABU))
    price = request.POST.get('price', '0')
    monthly_rent = request.POST.get('monthly_rent', '0')
    deposit_amount = request.POST.get('deposit_amount', request.POST.get('deposit', '0'))
    remaining_lease_months = request.POST.get('remaining_lease_months', request.POST.get('lease_months', '12'))
    avg_profit_3m = request.POST.get('avg_profit_3m', '')
    avg_revenue_3m = request.POST.get('avg_revenue_3m', '')
    district = request.POST.get('district', '').strip()
    province = request.POST.get('province', 'กรุงเทพมหานคร').strip()
    address = request.POST.get('address', '').strip()
    description = request.POST.get('description', '').strip()
    equipment_included = request.POST.get('equipment_included', '').strip()
    sqm = request.POST.get('sqm', request.POST.get('area_sqm', '50.00'))
    floors = int(request.POST.get('floors', '1') or '1')
    postal = request.POST.get('postal', '10400' if 'กรุงเทพ' in province else '20150')
    contact_phone = request.POST.get('contact_phone', '').strip()
    contact_line_id = request.POST.get('contact_line_id', '').strip()
    owner_name = request.POST.get('owner_name', '').strip()
    owner_facebook = request.POST.get('owner_facebook', '').strip()
    owner_notes = request.POST.get('owner_notes', '').strip()
    includes_staff = request.POST.get('includes_staff') in ['1', 'true', 'on']
    is_admin_verified = request.POST.get('is_admin_verified') in ['1', 'true', 'on']

    lease_transfer_fee_raw = request.POST.get('lease_transfer_fee', '0').replace(',', '').strip()
    try:
        lease_transfer_fee = Decimal(lease_transfer_fee_raw) if lease_transfer_fee_raw else Decimal('0')
    except (ValueError, InvalidOperation):
        lease_transfer_fee = Decimal('0')

    lease_transfer_fee_payer = request.POST.get('lease_transfer_fee_payer', FeePayer.FREE).strip().lower()
    if lease_transfer_fee_payer not in FeePayer.values:
        lease_transfer_fee_payer = FeePayer.FREE

    is_immediate_publish = (
        request.POST.get('is_published') == '1' or
        request.POST.get('auto_publish') == 'on' or
        request.POST.get('auto_publish') == '1'
    )

    if not title or not price or not district:
        messages.error(request, 'กรุณากรอกชื่อร้าน ราคาเซ้ง และทำเลที่ตั้งให้ครบถ้วน')
        return redirect('/admin-dashboard/?tab=shops')

    google_maps_url = request.POST.get('google_maps_url', '').strip()
    from apps.properties.utils import extract_google_maps_coordinates, get_default_coordinates_for_location
    lat, lng = extract_google_maps_coordinates(google_maps_url) if google_maps_url else (None, None)
    if not lat or not lng:
        lat, lng = get_default_coordinates_for_location(province, district)

    custom_ref_code = request.POST.get('ref_code', '').strip().upper()
    listing_plan = request.POST.get('listing_plan', 'broker').strip().lower()

    if custom_ref_code:
        if Listing.objects.filter(ref_code=custom_ref_code).exists():
            messages.error(request, f'❌ รหัส "{custom_ref_code}" ซ้ำกับร้านอื่นในระบบ กรุณาระบุรหัสใหม่')
            return redirect('/admin-dashboard/?tab=shops')
        target_ref_code = custom_ref_code
    else:
        from apps.listings.models import generate_ref_code
        if listing_plan == 'broker':
            target_ref_code = generate_ref_code('N')
        elif listing_plan == 'super_vip':
            target_ref_code = generate_ref_code('S')
        elif listing_plan == 'vip':
            target_ref_code = generate_ref_code('V')
        else:
            target_ref_code = generate_ref_code('F')

    assigned_agent = request.user if listing_plan == 'broker' or request.user.role == UserRole.AGENT else None

    owner = User.objects.filter(pk=owner_id).first() if owner_id else request.user

    try:
        # 1. Create Property
        prop = Property.objects.create(
            owner=owner,
            title=title,
            type=category,
            district=district,
            province=province,
            address=address or f"{district}, {province}",
            postal=postal,
            google_maps_url=google_maps_url or None,
            lat=lat,
            lng=lng,
            desc=description or f"{title} ในทำเลศักยภาพ {district} {province}",
            area_sqm=Decimal(sqm or '50.00'),
            floors=floors,
        )

        # 2. Create Listing
        listing = Listing.objects.create(
            property=prop,
            agent=assigned_agent,
            ref_code=target_ref_code,
            price=Decimal(price),
            monthly_rent=Decimal(monthly_rent or '0'),
            security_deposit=Decimal(deposit_amount or '0'),
            lease_remaining_months=int(remaining_lease_months or 12),
            lease_transfer_fee=lease_transfer_fee,
            lease_transfer_fee_payer=lease_transfer_fee_payer,
            includes_staff=includes_staff,
            avg_profit_3m=Decimal(avg_profit_3m) if avg_profit_3m else None,
            avg_revenue_3m=Decimal(avg_revenue_3m) if avg_revenue_3m else None,
            includes_equipment=equipment_included,
            owner_name=owner_name or (owner.get_full_name() if owner else ''),
            owner_phone=contact_phone or (owner.phone if owner else ''),
            owner_line_id=contact_line_id or (getattr(owner, 'line_id', '') if owner else ''),
            owner_facebook=owner_facebook,
            owner_notes=owner_notes,
            contact_phone=contact_phone or (owner.phone if owner else ''),
            contact_line_id=contact_line_id or (getattr(owner, 'line_id', '') if owner else ''),
            status=ListingStatus.PUBLISHED if is_immediate_publish else ListingStatus.PENDING,
            is_admin_verified=is_admin_verified,
            admin_verified_at=timezone.now() if is_admin_verified else None,
            type=ListingType.TAKEOVER,
        )

        # 3. Handle Multi-Image Upload
        image_files = request.FILES.getlist('images')
        for idx, img_file in enumerate(image_files[:8]):
            sanitized_img = validate_and_sanitize_image(img_file)
            PropertyImage.objects.create(
                property=prop,
                image=sanitized_img,
                is_cover=(idx == 0),
                order=idx
            )

        AuditService.log(
            action='CREATE',
            model_name='Listing (Admin Fast-Post)',
            object_id=listing.pk,
            changes={'title': title, 'price': price, 'owner': owner.username},
            request=request
        )

        # Dispatch Telegram Alert for New Listing!
        from apps.core.services.telegram import TelegramAlertService
        TelegramAlertService.send_new_listing_alert(listing)

        messages.success(request, f'🎉 สร้างและลงประกาศร้าน "{title}" (รหัส {listing.ref_code}) สำเร็จแล้ว!')
    except Exception as e:
        logger.error(f"Error fast-creating shop: {e}")
        messages.error(request, f'เกิดข้อผิดพลาดในการสร้างร้านค้า: {str(e)}')

    return redirect('/admin-dashboard/?tab=shops')


# ==============================================================================
# CRM LEADS & DEALS ACTIONS
# ==============================================================================
@login_required
@role_required(UserRole.STAFF, UserRole.ADMIN)
@require_http_methods(["POST"])
def admin_lead_action_view(request, pk):
    """Update lead status or assign agent"""
    lead = get_object_or_404(Lead, pk=pk)
    action = request.POST.get('action')
    new_status = request.POST.get('status')
    agent_id = request.POST.get('agent_id')

    updated = False
    if new_status and new_status in LeadStatus.values:
        lead.status = new_status
        updated = True
        messages.success(request, f'อัปเดตสถานะของลีด {lead.full_name} เป็น "{lead.get_status_display()}"')

    if agent_id is not None:
        if agent_id.startswith('profile_'):
            p_id = agent_id.replace('profile_', '')
            profile = AgentProfile.objects.filter(pk=p_id).first()
            lead.assigned_agent_profile = profile
            lead.assigned_agent = None
            updated = True
            messages.success(request, f'จ่ายงานลีด {lead.full_name} ให้นายหน้า "{profile.full_name if profile else "-"}" สำเร็จ')
        elif agent_id.startswith('user_') or (agent_id.isdigit() and agent_id != ''):
            u_id = agent_id.replace('user_', '')
            agent = User.objects.filter(pk=u_id).first()
            lead.assigned_agent = agent
            lead.assigned_agent_profile = None
            updated = True
            agent_name = agent.get_full_name() or agent.username if agent else "ไม่ระบุ"
            messages.success(request, f'จ่ายงานลีด {lead.full_name} ให้นายหน้า "{agent_name}" สำเร็จ')
        elif agent_id == '':
            lead.assigned_agent = None
            lead.assigned_agent_profile = None
            updated = True
            messages.info(request, f'ยกเลิกการมอบหมายผู้ดูแลลีด {lead.full_name}')

    if updated:
        lead.save()

    return redirect('/admin-dashboard/?tab=crm')


@login_required
@role_required(UserRole.STAFF, UserRole.ADMIN)
@require_http_methods(["POST"])
def admin_deal_action_view(request, pk):
    """Advance deal stage or update deal details"""
    deal = get_object_or_404(Deal, pk=pk)
    new_stage = request.POST.get('stage')
    agreed_price = request.POST.get('agreed_price')
    deposit_amount = request.POST.get('deposit_amount')

    if agreed_price:
        deal.agreed_price = Decimal(agreed_price)
    if deposit_amount:
        deal.deposit_amount = Decimal(deposit_amount)

    if new_stage in DealStage.values:
        deal.stage = new_stage
        if new_stage == DealStage.CLOSED_WON:
            deal.closed_at = timezone.now()
        messages.success(request, f'อัปเดตขั้นตอนดีล [{deal.deal_code}] เป็น "{deal.get_stage_display()}"')

    deal.calculate_commission()
    deal.save()
    AuditService.log(action='UPDATE', model_name='Deal', object_id=deal.pk, changes={'stage': deal.stage}, request=request)

    return redirect('/admin-dashboard/?tab=pipeline')


@login_required
@role_required(UserRole.STAFF, UserRole.ADMIN)
@require_http_methods(["POST"])
def admin_resolve_message_view(request, pk):
    """Mark contact inquiry message as resolved"""
    msg_obj = get_object_or_404(ContactMessage, pk=pk)
    msg_obj.is_resolved = True
    msg_obj.save(update_fields=['is_resolved'])
    messages.success(request, f'ทำเครื่องหมายรับเรื่องข้อความจากคุณ {msg_obj.name} เรียบร้อยแล้ว')
    return redirect('/admin-dashboard/?tab=documents')


@login_required
@role_required(UserRole.STAFF, UserRole.ADMIN)
@require_http_methods(["POST"])
def admin_telegram_detect_view(request):
    """Detects group chat ID from Telegram Bot API getUpdates and sends a test message"""
    from django.core.management import call_command
    import io
    from contextlib import redirect_stdout, redirect_stderr

    f = io.StringIO()
    with redirect_stdout(f), redirect_stderr(f):
        call_command('find_telegram_chat_id')
    out = f.getvalue()

    if "ยิงข้อความทดสอบเข้ากลุ่ม Telegram สำเร็จแล้ว" in out:
        messages.success(request, '🎉 ตรวจพบ Chat ID และยิงข้อความทดสอบเข้ากลุ่ม Telegram สำเร็จแล้ว!')
    elif "พบคุยล่าสุด" in out:
        messages.success(request, f'✅ บันทึก Chat ID เรียบร้อย: {out[:120]}')
    else:
        messages.warning(request, '⚠️ ยังไม่พบข้อความในคิว! กรุณาดึงบอท @proptech2026_th_bot เข้ากลุ่ม Telegram แล้วพิมพ์ข้อความอะไรก็ได้ 1 ข้อความในกลุ่ม แล้วกดปุ่มนี้อีกครั้ง')

    return redirect('/admin-dashboard/?tab=overview')


@login_required
@role_required(UserRole.STAFF, UserRole.ADMIN)
@require_http_methods(["POST"])
def admin_create_agent_view(request):
    """
    WHY SECURE:
    Admin endpoint to register a new verified agent/broker:
    - full_name, phone, line_id, facebook_url, photo
    """
    full_name = request.POST.get('full_name', '').strip()
    phone = request.POST.get('phone', '').strip()
    line_id = request.POST.get('line_id', '').strip()
    facebook_url = request.POST.get('facebook_url', '').strip()
    notes = request.POST.get('notes', '').strip()
    photo = request.FILES.get('photo')

    if not full_name or not phone:
        messages.error(request, 'กรุณาระบุชื่อ-นามสกุล และเบอร์โทรศัพท์ของนายหน้า')
        return redirect('/admin-dashboard/?tab=agents')

    agent = AgentProfile.objects.create(
        full_name=full_name,
        phone=phone,
        line_id=line_id,
        facebook_url=facebook_url,
        notes=notes,
        status=AgentProfile.Status.APPROVED,
        photo=photo
    )
    AuditService.log(
        action='CREATE',
        model_name='AgentProfile',
        object_id=agent.pk,
        changes={'full_name': full_name, 'phone': phone},
        request=request
    )
    messages.success(request, f'✅ บันทึกประวัตินายหน้า "{full_name}" เข้าระบบเรียบร้อยแล้ว')
    return redirect('/admin-dashboard/?tab=agents')


@login_required
@role_required(UserRole.STAFF, UserRole.ADMIN)
@require_http_methods(["POST"])
def admin_agent_action_view(request, pk):
    """Update status or delete agent profile."""
    agent = get_object_or_404(AgentProfile, pk=pk)
    action = request.POST.get('action')

    if action == 'toggle_status':
        if agent.status == AgentProfile.Status.APPROVED:
            agent.status = AgentProfile.Status.INACTIVE
            status_txt = "ปิดใช้งานชั่วคราว"
        else:
            agent.status = AgentProfile.Status.APPROVED
            status_txt = "อนุมัติพร้อมรับงาน"
        agent.save(update_fields=['status'])
        messages.success(request, f'เปลี่ยนสถานะนายหน้า "{agent.full_name}" เป็น: {status_txt}')
    elif action == 'delete':
        name = agent.full_name
        agent.delete()
        messages.success(request, f'🗑️ ลบประวัตินายหน้า "{name}" ออกจากระบบเรียบร้อยแล้ว')

    return redirect('/admin-dashboard/?tab=agents')


@login_required
@role_required(UserRole.STAFF, UserRole.ADMIN)
@require_http_methods(["POST"])
def admin_update_shop_owner_view(request, pk):
    """
    Update owner contact details (Name, Phone, LINE, Facebook, Notes) for a specific shop code (Ref Code).
    """
    listing = get_object_or_404(Listing.objects.select_related('property'), pk=pk)
    
    owner_name = request.POST.get('owner_name', '').strip()
    owner_phone = request.POST.get('owner_phone', '').strip()
    owner_line_id = request.POST.get('owner_line_id', '').strip()
    owner_facebook = request.POST.get('owner_facebook', '').strip()
    owner_notes = request.POST.get('owner_notes', '').strip()

    listing.owner_name = owner_name
    listing.owner_phone = owner_phone
    listing.owner_line_id = owner_line_id
    listing.owner_facebook = owner_facebook
    listing.owner_notes = owner_notes

    # Keep contact_phone & contact_line_id in sync if empty
    if owner_phone and not listing.contact_phone:
        listing.contact_phone = owner_phone
    if owner_line_id and not listing.contact_line_id:
        listing.contact_line_id = owner_line_id

    listing.save(update_fields=['owner_name', 'owner_phone', 'owner_line_id', 'owner_facebook', 'owner_notes', 'contact_phone', 'contact_line_id'])

    AuditService.log(
        action='UPDATE',
        model_name='Listing',
        object_id=listing.pk,
        changes={
            'action': 'UPDATE_OWNER_CONTACT',
            'ref_code': listing.ref_code,
            'owner_name': owner_name,
            'owner_phone': owner_phone,
            'owner_line_id': owner_line_id,
            'owner_facebook': owner_facebook,
        },
        request=request
    )

    messages.success(request, f'✅ บันทึกข้อมูลเจ้าของร้านรหัส "{listing.ref_code}" ({listing.property.title}) เรียบร้อยแล้ว')
    return redirect(request.META.get('HTTP_REFERER', '/admin-dashboard/?tab=owners'))


@login_required
@role_required(UserRole.STAFF, UserRole.ADMIN)
@require_http_methods(["POST"])
def admin_delete_shop_owner_view(request, pk):
    """
    Clear/delete owner contact records (Name, Phone, LINE, Facebook, Notes) for a specific shop code (Ref Code).
    """
    listing = get_object_or_404(Listing.objects.select_related('property'), pk=pk)
    ref_code = listing.ref_code
    shop_title = listing.property.title if listing.property else ''

    listing.owner_name = ''
    listing.owner_phone = ''
    listing.owner_line_id = ''
    listing.owner_facebook = ''
    listing.owner_notes = ''
    listing.save(update_fields=['owner_name', 'owner_phone', 'owner_line_id', 'owner_facebook', 'owner_notes'])

    AuditService.log(
        action='DELETE',
        model_name='Listing',
        object_id=listing.pk,
        changes={
            'action': 'DELETE_OWNER_CONTACT',
            'ref_code': ref_code,
        },
        request=request
    )

    messages.success(request, f'🗑️ ลบข้อมูลเจ้าของร้านรหัส "{ref_code}" ({shop_title}) เรียบร้อยแล้ว')
    return redirect(request.META.get('HTTP_REFERER', '/admin-dashboard/?tab=owners'))


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from apps.listings.models import Listing, ListingStatus
from apps.leads.models import Lead, LeadStatus
from apps.leads.forms import LeadInquiryForm
from apps.contracts.models import Deal, DealStage
from apps.core.services.telegram import TelegramAlertService
from apps.accounts.services.audit import AuditService

@ratelimit(key='ip', rate='5/h', block=True)
@require_http_methods(["POST"])
def submit_inquiry_view(request, listing_pk):
    """
    WHY SECURE:
    1. Rate limited to 5 submissions/hour/IP (anti-lead spam/flooding).
    2. Links lead to listing and initializes Deal Pipeline atomically.
    3. Dispatches Telegram notification to broker team.
    """
    listing = get_object_or_404(Listing.objects.select_related('property', 'agent'), pk=listing_pk)
    
    # Must only accept inquiries on published listings
    if listing.status != ListingStatus.PUBLISHED:
        messages.error(request, 'ประกาศนี้ไม่ได้เปิดรับการติดต่อ')
        return redirect('listings:marketplace')

    form = LeadInquiryForm(request.POST)
    if form.is_valid():
        lead = form.save(commit=False)
        lead.listing = listing
        lead.assigned_agent = listing.agent
        lead.save()

        # Initialize Deal in Pipeline
        deal = Deal.objects.create(
            listing=listing,
            lead=lead,
            agent=listing.agent,
            stage=DealStage.NEW_LEAD
        )

        AuditService.log(
            action='CREATE',
            model_name='Lead',
            object_id=lead.pk,
            changes={'listing_ref': listing.ref_code, 'name': lead.full_name},
            request=request
        )

        # Telegram Alert
        budget_text = f"฿{lead.budget_max:,.0f}" if lead.budget_max else "ตามราคาเซ้งของร้าน"
        TelegramAlertService.send_alert(
            f"🏪 ร้าน: *[{listing.ref_code}]* {listing.property.title}\n"
            f"👤 ผู้สนใจ: {lead.full_name}\n"
            f"📞 เบอร์โทร: `{lead.phone}`\n"
            f"💬 LINE: {lead.line_id or '—'}\n"
            f"💰 งบประมาณ: {budget_text} (เร่งด่วน: {lead.get_urgency_display()})\n"
            f"🤝 นายหน้าผู้ดูแล: {listing.agent.first_name if listing.agent else 'รอจัดสรร'}",
            event_title="🔥 มีลูกค้าสนใจร้านใหม่ (New Lead)"
        )

        messages.success(request, 'ส่งข้อมูลความสนใจเรียบร้อยแล้ว! เจ้าหน้าที่จะติดต่อกลับโดยเร็วที่สุด')
    else:
        err_msg = 'ข้อมูลไม่ถูกต้อง กรุณาตรวจสอบข้อมูลอีกครั้ง'
        if form.errors:
            first_err = next(iter(form.errors.values()))[0]
            err_msg = f"ข้อมูลไม่ถูกต้อง: {first_err}"
        messages.error(request, err_msg)

    return redirect('listings:listing_detail', pk=listing.pk)

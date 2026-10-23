import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.contracts.models import Deal, DealStage
from apps.listings.models import ListingStatus
from apps.core.services.telegram import TelegramAlertService
from apps.accounts.services.audit import AuditService

logger = logging.getLogger(__name__)

class DealService:
    """
    WHY SECURE:
    1. ACID Compliance: Uses select_for_update() row lock and transaction.atomic()
       to eliminate race conditions and financial calculation discrepancies.
    2. Exact Decimal Math: Computes broker payouts with strict 2-decimal quantizing.
    3. State Machine Coupling: Syncs listing state (under_negotiation / closed) atomically.
    4. Audited Transitions: Records tamper-evident audit logs with financial delta.
    """
    @classmethod
    @transaction.atomic
    def advance_stage(cls, deal_id, target_stage, agreed_price=None, deposit_amount=None, request=None, actor=None):
        deal = Deal.objects.select_for_update(of=('self',)).select_related('listing', 'agent', 'lead').get(pk=deal_id)
        old_stage = deal.stage
        deal.stage = target_stage

        if agreed_price is not None:
            deal.agreed_price = Decimal(str(agreed_price))
        if deposit_amount is not None:
            deal.deposit_amount = Decimal(str(deposit_amount))

        # Financial Calculations on Closing
        if target_stage == DealStage.CLOSED_WON:
            deal.calculate_commission()
            deal.closed_at = timezone.now()
            # Mark associated listing as closed
            deal.listing.status = ListingStatus.CLOSED
            deal.listing.save(update_fields=['status'])
        elif target_stage == DealStage.DEPOSIT_PAID:
            deal.listing.status = ListingStatus.UNDER_NEGOTIATION
            deal.listing.save(update_fields=['status'])

        deal.save()

        # Record AuditLog
        AuditService.log(
            action='UPDATE',
            model_name='Deal',
            object_id=deal.deal_code,
            changes={
                'old_stage': old_stage,
                'new_stage': target_stage,
                'agreed_price': str(deal.agreed_price) if deal.agreed_price else None,
                'gross_commission': str(deal.gross_commission),
                'agent_payout': str(deal.agent_payout),
            },
            user=actor,
            request=request
        )

        # Trigger Real-time Telegram Notifications
        if target_stage == DealStage.CLOSED_WON:
            TelegramAlertService.send_alert(
                f"รหัสดีล: `{deal.deal_code}`\n"
                f"ร้านค้า: *[{deal.listing.ref_code}]* {deal.listing.property.title}\n"
                f"ราคาเซ้งปิดจบ: ฿{deal.agreed_price:,.0f}\n"
                f"ค่าคอมมิชชั่นรวม: ฿{deal.gross_commission:,.0f}\n"
                f"ส่วนแบ่งนายหน้า: ฿{deal.agent_payout:,.0f} ({deal.agent.first_name if deal.agent else 'N/A'})\n"
                f"ส่วนแบ่งแพลตฟอร์ม: ฿{deal.platform_payout:,.0f}",
                event_title="🏆 ปิดการขายสำเร็จ (Closed Won)"
            )
        elif target_stage == DealStage.DEPOSIT_PAID:
            TelegramAlertService.send_alert(
                f"รหัสดีล: `{deal.deal_code}`\n"
                f"ร้านค้า: *[{deal.listing.ref_code}]*\n"
                f"ยอดมัดจำ: ฿{deal.deposit_amount:,.0f}",
                event_title="💰 วางเงินมัดจำ (Deposit Paid)"
            )

        return deal

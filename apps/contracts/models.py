import random
import string
import datetime
import os
import uuid
from decimal import Decimal
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from apps.listings.models import Listing
from apps.leads.models import Lead

User = get_user_model()

class DealStage(models.TextChoices):
    NEW_LEAD = 'new_lead', _('1. ลีดใหม่สนใจร้าน')
    CONTACTED = 'contacted', _('2. โทรติดต่อพูดคุยแล้ว')
    SITE_VISIT_SCHEDULED = 'site_visit_scheduled', _('3. นัดหมายดูร้านจริง')
    SITE_VISIT_COMPLETED = 'site_visit_completed', _('4. ชมร้านค้าเรียบร้อย')
    NEGOTIATION = 'negotiation', _('5. กำลังต่อรองราคา/เงื่อนไข')
    DEPOSIT_PAID = 'deposit_paid', _('6. วางเงินมัดจำแล้ว')
    CONTRACT_SIGNING = 'contract_signing', _('7. นัดเซ็นสัญญาจะซื้อจะขาย')
    CLOSED_WON = 'closed_won', _('8. ปิดดีลสำเร็จ (Closed Won)')
    CLOSED_LOST = 'closed_lost', _('9. ดีลยกเลิก / ไม่สำเร็จ (Closed Lost)')

class DocumentType(models.TextChoices):
    TAKEOVER_CONTRACT = 'takeover_contract', _('สัญญาจะซื้อจะขายสิทธิการเช่า (Takeover Agreement)')
    ORIGINAL_LEASE = 'original_lease', _('สัญญาเช่าเดิมกับเจ้าของตึก/นิติบุคคล')
    DEPOSIT_SLIP = 'deposit_slip', _('หลักฐานการโอนเงินมัดจำ')
    SELLER_ID = 'seller_id', _('สำเนาบัตรประชาชนผู้ให้เซ้ง')
    BUYER_ID = 'buyer_id', _('สำเนาบัตรประชาชนผู้รับเซ้ง')
    INVENTORY_LIST = 'inventory_list', _('รายการตรวจนับทรัพย์สินและอุปกรณ์')

def secure_private_upload_path(instance, filename):
    """
    WHY SECURE:
    Stores contracts in private directory (media/private/contracts/YYYY/MM/<uuid>.ext).
    Served strictly through Nginx X-Accel-Redirect after authentication.
    """
    ext = os.path.splitext(filename)[1].lower()
    now = datetime.datetime.now()
    clean_uuid = uuid.uuid4().hex
    return f"private/contracts/{now:%Y}/{now:%m}/{clean_uuid}{ext}"

def generate_deal_code():
    random_str = ''.join(random.choices(string.digits, k=4))
    year = datetime.datetime.now().year
    return f"DEAL-{year}-{random_str}"

class Deal(models.Model):
    """
    WHY SECURE:
    - Finite State Machine tracking broker pipeline stages.
    - Financial precision using DecimalField with ACID transactions.
    - Commission splits calculated deterministically.
    """
    deal_code = models.CharField(max_length=30, unique=True, db_index=True)
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='deals')
    lead = models.ForeignKey(Lead, on_delete=models.SET_NULL, null=True, blank=True, related_name='deals')
    agent = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='agent_deals')
    assigned_agent_profile = models.ForeignKey(
        'accounts.AgentProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contract_deals',
        help_text=_('นายหน้าผู้ดูแลดีล')
    )

    stage = models.CharField(
        max_length=30,
        choices=DealStage.choices,
        default=DealStage.NEW_LEAD,
        db_index=True
    )
    closed_by = models.CharField(
        max_length=20,
        choices=[
            ('platform', _('แพลตฟอร์มปิดเอง (รับเต็ม 5%)')),
            ('agent', _('นายหน้าเป็นผู้ปิด (แบ่ง 2.5% / 2.5%)'))
        ],
        default='platform',
        db_index=True,
        help_text=_('ผู้ปิดการขายดีลนี้')
    )
    
    # Financial settlement figures
    agreed_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('ราคาเซ้งตกลงสุดท้าย (บาท)')
    )
    deposit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('เงินมัดจำที่ชำระแล้ว (บาท)')
    )

    # Commission Calculation Engine (5% total: 5% platform vs 2.5%/2.5% split)
    commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        help_text=_('อัตราค่าคอมมิชชั่นรวม (%) เช่น 5%')
    )
    agent_commission_share = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('50.00'),
        help_text=_('ส่วนแบ่งของนายหน้า (%) เช่น 50% ของคอมฯ รวม')
    )
    gross_commission = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('ยอดค่าคอมมิชชั่นรวม 5% ที่เรียกเก็บได้ (บาท)')
    )
    agent_payout = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('เงินค่าคอมมิชชั่นจ่ายให้นายหน้า (บาท) [2.5%]')
    )
    platform_payout = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text=_('ส่วนแบ่งรายได้เข้าแพลตฟอร์ม (บาท) [2.5% หรือ 5%]')
    )

    def calculate_commission(self):
        """
        Calculates 5% total fee:
        - Platform closed: 100% of 5% goes to Platform.
        - Agent closed: 50% (2.5%) goes to Platform, 50% (2.5%) goes to Agent.
        """
        if not self.agreed_price:
            return
        self.commission_rate = Decimal('5.00')
        self.gross_commission = (Decimal(str(self.agreed_price)) * Decimal('0.05')).quantize(Decimal('0.01'))
        if self.closed_by == 'platform':
            self.platform_payout = self.gross_commission
            self.agent_payout = Decimal('0.00')
        else:
            half = (self.gross_commission / Decimal('2')).quantize(Decimal('0.01'))
            self.platform_payout = half
            self.agent_payout = self.gross_commission - half


    site_visit_date = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Deal Pipeline')
        verbose_name_plural = _('Deal Pipelines')

    def save(self, *args, **kwargs):
        if not self.deal_code:
            while True:
                candidate = generate_deal_code()
                if not Deal.objects.filter(deal_code=candidate).exists():
                    self.deal_code = candidate
                    break
        super().save(*args, **kwargs)

    def calculate_commission(self):
        """Calculates commission splits deterministically."""
        if self.agreed_price and self.agreed_price > 0:
            self.gross_commission = (self.agreed_price * (self.commission_rate / Decimal('100.00'))).quantize(Decimal('0.01'))
            self.agent_payout = (self.gross_commission * (self.agent_commission_share / Decimal('100.00'))).quantize(Decimal('0.01'))
            self.platform_payout = (self.gross_commission - self.agent_payout).quantize(Decimal('0.01'))

    def __str__(self):
        return f"[{self.deal_code}] {self.listing.ref_code} ({self.get_stage_display()})"

class ContractDocument(models.Model):
    """
    WHY SECURE:
    - Encapsulates sensitive legal files (takeover contracts, lease agreements, IDs).
    - Stored in private directory; never exposed via direct static URL.
    """
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name='documents')
    type = models.CharField(max_length=30, choices=DocumentType.choices)
    file = models.FileField(upload_to=secure_private_upload_path)
    file_name_display = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    is_verified = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = _('Contract Document')
        verbose_name_plural = _('Contract Documents')

    def __str__(self):
        return f"{self.get_type_display()} - {self.deal.deal_code}"

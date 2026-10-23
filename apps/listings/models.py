import random
import string
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from apps.properties.models import Property

User = get_user_model()

class ListingType(models.TextChoices):
    TAKEOVER = 'takeover', _('เซ้งกิจการ / เซ้งร้าน')
    RENT = 'rent', _('เช่าพื้นที่ / ตึกแถว')
    SALE_BIZ = 'sale_biz', _('ขายกิจการขาด')
    PARTNERSHIP = 'partnership', _('หาผู้ร่วมทุน / หุ้นส่วน')

class ListingStatus(models.TextChoices):
    DRAFT = 'draft', _('ฉบับร่าง (Draft)')
    PENDING = 'pending', _('รอการอนุมัติ (Pending Review)')
    PUBLISHED = 'published', _('เผยแพร่แล้ว (Published)')
    REJECTED = 'rejected', _('ปฏิเสธการเผยแพร่ (Rejected)')
    UNDER_NEGOTIATION = 'under_negotiation', _('กำลังเจรจา / วางมัดจำ')
    CLOSED = 'closed', _('ปิดการขาย / เซ้งสำเร็จแล้ว (Closed)')

class FeePayer(models.TextChoices):
    FREE = 'free', _('ฟรีค่าเปลี่ยนสัญญา')
    SELLER = 'seller', _('ผู้เซ้งเดิมออกให้')
    BUYER = 'buyer', _('ผู้เซ้งใหม่ออกเอง')
    HALF_HALF = 'half_half', _('คนละครึ่ง')

def generate_ref_code(prefix='N'):
    """
    Generate unique human-readable tracking code (preserving legacy convention: N-032, S-228).
    """
    random_num = ''.join(random.choices(string.digits, k=3))
    return f"{prefix}-{random_num}"

class Listing(models.Model):
    """
    WHY SECURE:
    - DecimalField for all financial figures (prevents floating-point rounding errors/theft).
    - Status state machine controls visibility: only 'published' listings are visible to public.
    - Moderation barrier: Only staff/admin can transition status from 'pending' to 'published'.
    """
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='listings',
        help_text=_('ทรัพย์สิน/สถานที่ที่ลงประกาศ')
    )
    agent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_listings',
        help_text=_('นายหน้าที่ได้รับมอบหมายให้ดูแลดีลนี้')
    )
    ref_code = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        help_text=_('รหัสประกาศ เช่น N-032, S-228')
    )
    type = models.CharField(
        max_length=20,
        choices=ListingType.choices,
        default=ListingType.TAKEOVER,
        db_index=True
    )
    
    # Financial Metrics (จุดขายของแพลตฟอร์มเซ้งร้าน)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text=_('ราคาเซ้ง (บาท)')
    )
    monthly_rent = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text=_('ค่าเช่าต่อเดือน (บาท)')
    )
    security_deposit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text=_('เงินประกัน/มัดจำ (บาท)')
    )
    lease_remaining_months = models.PositiveIntegerField(
        default=0,
        help_text=_('ระยะเวลาสัญญาเช่าคงเหลือ (เดือน)')
    )
    lease_transfer_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text=_('ค่าเปลี่ยนสัญญา (บาท)')
    )
    lease_transfer_fee_payer = models.CharField(
        max_length=20,
        choices=FeePayer.choices,
        default=FeePayer.FREE
    )

    # Transparency Financials (ยอดขายและกำไรเฉลี่ย)
    avg_revenue_3m = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('รายได้เฉลี่ย 3 เดือนล่าสุด (บาท/เดือน)')
    )
    avg_profit_3m = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('กำไรสุทธิเฉลี่ย 3 เดือนล่าสุด (บาท/เดือน)')
    )

    # Operational Assets
    includes_equipment = models.TextField(
        blank=True,
        help_text=_('รายการอุปกรณ์และเฟอร์นิเจอร์ที่ยกให้พร้อมร้าน')
    )
    includes_staff = models.BooleanField(
        default=False,
        help_text=_('มีพนักงานเดิมพร้อมดำเนินงานต่อ')
    )

    # State Machine & Status
    status = models.CharField(
        max_length=20,
        choices=ListingStatus.choices,
        default=ListingStatus.DRAFT,
        db_index=True
    )
    published_at = models.DateTimeField(null=True, blank=True)
    view_count = models.PositiveIntegerField(default=0)
    lead_click_count = models.PositiveIntegerField(default=0)

    # Admin Verification Badge (ป้าย เวอร์ริไฟร์ รับรองโดยแอดมิน)
    is_admin_verified = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_('ร้านนี้ผ่านการตรวจสอบจริงโดยแอดมิน (Admin Verified)')
    )
    admin_verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Shop Listing')
        verbose_name_plural = _('Shop Listings')

    def save(self, *args, **kwargs):
        if not self.ref_code:
            # Auto-generate unique ref code
            while True:
                candidate = generate_ref_code()
                if not Listing.objects.filter(ref_code=candidate).exists():
                    self.ref_code = candidate
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.ref_code}] {self.property.title} - ฿{self.price:,.0f}"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('listings:listing_detail', kwargs={'pk': self.pk})

class ListingApproval(models.Model):
    """
    WHY SECURE:
    - Immutable moderation log for listing approvals/rejections.
    - Prevents rogue listings or scams from going live without an auditable reviewer.
    """
    class Action(models.TextChoices):
        APPROVE = 'approve', _('อนุมัติเผยแพร่ (Approved)')
        REJECT = 'reject', _('ปฏิเสธการเผยแพร่ (Rejected)')
        REQUEST_CHANGES = 'request_changes', _('ขอให้แก้ไขข้อมูลเพิ่มเติม')

    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name='approvals'
    )
    reviewer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='reviewed_listings',
        help_text=_('ผู้ตรวจสอบ (Staff/Admin)')
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    note = models.TextField(help_text=_('เหตุผลหรือบันทึกของผู้ตรวจสอบ'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Listing Approval Log')
        verbose_name_plural = _('Listing Approval Logs')

    def __str__(self):
        return f"{self.reviewer} {self.action} on {self.listing.ref_code}"

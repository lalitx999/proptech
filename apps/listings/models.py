import builtins
import re
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

def generate_ref_code(prefix='F'):
    """
    Generate unique sequential human-readable tracking code:
    - โพสต์ฟรี: รหัส F รันอัตโนมัติ เริ่มต้น F001, F002, ...
    - โพสต์ VIP (1,000 บาท): รหัส V รันอัตโนมัติ เริ่มต้น V001, V002, ...
    - แอดมินเป็นนายหน้า: รหัส N รันเองหรืออัตโนมัติ เริ่มต้น N001, N002, ...
    - โพสต์ Super VIP (5,000 บาท): รหัส S รันเองหรืออัตโนมัติ เริ่มต้น S001, S002, ...
    """
    prefix = prefix.upper().strip() if prefix else 'F'
    existing_codes = Listing.objects.filter(
        ref_code__istartswith=prefix
    ).values_list('ref_code', flat=True)

    max_num = 0
    pattern = re.compile(rf'^{re.escape(prefix)}[-\s]?(\d+)$', re.IGNORECASE)
    for code in existing_codes:
        if code:
            match = pattern.match(code.strip())
            if match:
                try:
                    num = int(match.group(1))
                    if num > max_num:
                        max_num = num
                except ValueError:
                    pass

    next_num = max_num + 1
    candidate = f"{prefix}{next_num:03d}"

    while Listing.objects.filter(ref_code=candidate).exists():
        next_num += 1
        candidate = f"{prefix}{next_num:03d}"

    return candidate

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
    contact_phone = models.CharField(
        max_length=30,
        blank=True,
        help_text=_('เบอร์โทรศัพท์ติดต่อสำหรับประกาศนี้')
    )
    contact_line_id = models.CharField(
        max_length=100,
        blank=True,
        help_text=_('LINE ID สำหรับติดต่อประกาศนี้')
    )

    # Shop Owner Contact Record (ทะเบียนข้อมูลเจ้าของร้านแต่ละรหัส - สำหรับ Admin)
    owner_name = models.CharField(
        max_length=150,
        blank=True,
        help_text=_('ชื่อ-นามสกุล เจ้าของร้าน')
    )
    owner_phone = models.CharField(
        max_length=50,
        blank=True,
        help_text=_('เบอร์โทรศัพท์เจ้าของร้าน')
    )
    owner_line_id = models.CharField(
        max_length=100,
        blank=True,
        help_text=_('LINE ID เจ้าของร้าน')
    )
    owner_facebook = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Facebook เจ้าของร้าน / ลิงก์โปรไฟล์')
    )
    owner_notes = models.TextField(
        blank=True,
        help_text=_('บันทึกข้อมูลเจ้าของร้าน / เงื่อนไขพิเศษ')
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

    # Social & Video Review Links (YouTube, TikTok, Facebook)
    youtube_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text=_('ลิงก์คลิป YouTube รีวิวร้าน (เช่น https://www.youtube.com/watch?v=... หรือ https://youtu.be/...)')
    )
    tiktok_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text=_('ลิงก์คลิป TikTok รีวิวร้าน (เช่น https://www.tiktok.com/@.../video/...)')
    )
    facebook_post_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text=_('ลิงก์โพสต์ Facebook หรือเพจร้าน')
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Shop Listing')
        verbose_name_plural = _('Shop Listings')

    def save(self, *args, **kwargs):
        if not self.ref_code:
            # Auto-generate unique sequential ref code
            prefix = 'F'
            if self.agent_id:
                prefix = 'N'
            elif hasattr(self, 'property') and self.property and self.property.owner:
                owner = self.property.owner
                if getattr(owner, 'membership_tier', '') == 'SUPER_VIP' or getattr(owner, 'is_super_vip_active', False):
                    prefix = 'S'
                elif getattr(owner, 'is_vip_active', False) or getattr(owner, 'is_vip', False) or getattr(owner, 'membership_tier', '') == 'VIP':
                    prefix = 'V'
                else:
                    prefix = 'F'
            self.ref_code = generate_ref_code(prefix)
        else:
            self.ref_code = self.ref_code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.ref_code}] {self.property.title} - ฿{self.price:,.0f}"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('listings:listing_detail', kwargs={'pk': self.pk})

    @builtins.property
    def schema_availability(self):
        """
        WHY SEO / AEO CRITICAL:
        The schema.org `Offer.availability` value must mirror the real deal state. A
        hardcoded "InStock" keeps telling Google (and AI answer engines) that an already
        sold-out shop is still available, which destroys trust signals and can trigger
        rich-result penalties.
        """
        if self.status == ListingStatus.CLOSED:
            return 'https://schema.org/SoldOut'
        if self.status == ListingStatus.UNDER_NEGOTIATION:
            return 'https://schema.org/LimitedAvailability'
        if self.status == ListingStatus.PUBLISHED:
            return 'https://schema.org/InStock'
        return 'https://schema.org/OutOfStock'

    @builtins.property
    def offer_valid_until(self):
        """
        Rolling 12-month validity date for the schema.org Offer node.

        WHY: `Offer.priceValidUntil` must never be a hardcoded future year that silently
        expires; deriving it from the last modification keeps the structured data valid
        for every listing, forever.
        """
        from datetime import timedelta
        from django.utils import timezone
        base = self.updated_at or self.created_at or timezone.now()
        return (base + timedelta(days=365)).date()

    @builtins.property
    def display_owner_name(self):
        if self.owner_name:
            return self.owner_name
        if hasattr(self, 'property') and self.property and self.property.owner:
            full = self.property.owner.get_full_name()
            return full if full else self.property.owner.username
        return '-'

    @builtins.property
    def display_owner_phone(self):
        if self.owner_phone:
            return self.owner_phone
        if self.contact_phone:
            return self.contact_phone
        if hasattr(self, 'property') and self.property and self.property.owner and self.property.owner.phone:
            return self.property.owner.phone
        return '-'

    @builtins.property
    def display_owner_line_id(self):
        if self.owner_line_id:
            return self.owner_line_id
        if self.contact_line_id:
            return self.contact_line_id
        if hasattr(self, 'property') and self.property and self.property.owner and self.property.owner.line_id:
            return self.property.owner.line_id
        return '-'

    @builtins.property
    def display_owner_facebook(self):
        return self.owner_facebook or '-'

    @builtins.property
    def youtube_embed_url(self):
        """Extract YouTube video ID and return embed URL if valid."""
        if not self.youtube_url:
            return None
        import re
        match = re.search(r'(?:youtu\.be\/|v\/|u\/\w\/|embed\/|watch\?v=|shorts\/|&v=)([^#&?]+)', self.youtube_url)
        if match:
            return f"https://www.youtube.com/embed/{match.group(1)}"
        return None

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


class ShopOwnerRecord(models.Model):
    """
    WHY SECURE & PRACTICAL:
    Raw shop owner contacts recorded by Admin directly (before or without a post/listing).
    Admin can input raw owner data first and convert to listing / fast post later.
    """
    owner_name = models.CharField(max_length=150, help_text=_('ชื่อ-นามสกุล เจ้าของร้าน'))
    owner_phone = models.CharField(max_length=50, blank=True, help_text=_('เบอร์โทรศัพท์'))
    owner_line_id = models.CharField(max_length=100, blank=True, help_text=_('LINE ID'))
    owner_facebook = models.CharField(max_length=255, blank=True, help_text=_('Facebook / ลิงก์โปรไฟล์'))
    shop_name = models.CharField(max_length=255, blank=True, help_text=_('ชื่อร้าน / กิจการ'))
    category = models.CharField(max_length=100, blank=True, help_text=_('หมวดหมู่ร้านค้า'))
    location = models.CharField(max_length=255, blank=True, help_text=_('ทำเลที่ตั้ง / เขต / จังหวัด'))
    expected_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('ราคาเซ้งโดยประมาณ (บาท)')
    )
    monthly_rent = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('ค่าเช่า/เดือน (บาท)')
    )
    notes = models.TextField(blank=True, help_text=_('ข้อมูลดิบ / รายละเอียด / เงื่อนไขเจ้าของร้าน'))
    
    # Optional link to listing when post is created
    listing = models.ForeignKey(
        'Listing',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='raw_owner_records',
        help_text=_('โพสต์ประกาศที่สร้างจากข้อมูลนี้ (ถ้ามี)')
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_owner_records'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Shop Owner Record')
        verbose_name_plural = _('Shop Owner Records')

    def __str__(self):
        return f"{self.owner_name} ({self.shop_name or 'ไม่ระบุชื่อร้าน'})"

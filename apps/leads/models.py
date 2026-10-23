from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from apps.listings.models import Listing

User = get_user_model()

class LeadUrgency(models.TextChoices):
    IMMEDIATE = 'immediate', _('ด่วนที่สุด (ภายใน 1 เดือน)')
    ONE_TO_THREE_MONTHS = '1_3_months', _('ภายใน 1-3 เดือน')
    LOOKING = 'just_looking', _('กำลังสำรวจตลาด / เปรียบเทียบ')

class LeadStatus(models.TextChoices):
    NEW = 'new', _('ลีดใหม่ (New)')
    CONTACTED = 'contacted', _('ติดต่อแล้ว (Contacted)')
    SITE_VISIT = 'site_visit', _('นัดดูร้านแล้ว (Site Visit)')
    QUALIFIED = 'qualified', _('มีศักยภาพสูง (Qualified)')
    CLOSED = 'closed', _('ปิดการขาย (Closed)')
    LOST = 'lost', _('ยกเลิก / ไม่สนใจ (Lost)')

class Lead(models.Model):
    """
    WHY SECURE:
    - Customer CRM lead tracking with agent assignment isolation.
    - Captures phone, Line ID, and budget preferences for deal pipeline initiation.
    """
    listing = models.ForeignKey(
        Listing,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='leads',
        help_text=_('ร้านค้าที่สนใจ')
    )
    full_name = models.CharField(max_length=150, help_text=_('ชื่อ-นามสกุล ผู้สนใจ'))
    phone = models.CharField(max_length=20, help_text=_('เบอร์โทรศัพท์'))
    line_id = models.CharField(max_length=50, blank=True, help_text=_('LINE ID'))
    email = models.EmailField(blank=True)
    
    budget_max = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('งบประมาณสูงสุด (บาท)')
    )
    urgency = models.CharField(
        max_length=30,
        choices=LeadUrgency.choices,
        default=LeadUrgency.IMMEDIATE
    )
    status = models.CharField(
        max_length=30,
        choices=LeadStatus.choices,
        default=LeadStatus.NEW,
        db_index=True
    )
    assigned_agent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_leads',
        help_text=_('นายหน้าที่ได้รับมอบหมายให้ดูแลลีดนี้')
    )
    notes = models.TextField(blank=True, help_text=_('บันทึกการพูดคุย / ความต้องการพิเศษ'))
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Customer Lead')
        verbose_name_plural = _('Customer Leads')

    def __str__(self):
        target = f"[{self.listing.ref_code}]" if self.listing else ""
        return f"{self.full_name} ({self.phone}) {target}"

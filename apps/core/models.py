from django.db import models
from django.utils.translation import gettext_lazy as _

class ContactMessage(models.Model):
    """
    Customer Contact Inquiries received via /contact/ page.
    """
    name = models.CharField(max_length=150, help_text=_('ชื่อผู้ติดต่อ'))
    phone = models.CharField(max_length=30, help_text=_('เบอร์โทรศัพท์'))
    email = models.EmailField(blank=True, help_text=_('อีเมล (ถ้ามี)'))
    subject = models.CharField(max_length=200, help_text=_('หัวข้อติดต่อ'))
    message = models.TextField(help_text=_('ข้อความรายละเอียด'))
    is_resolved = models.BooleanField(default=False, help_text=_('เจ้าหน้าที่รับเรื่องแล้ว'))
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Contact Message')
        verbose_name_plural = _('Contact Messages')

    def __str__(self):
        return f"[{self.created_at:%d/%m/%Y}] {self.name} - {self.subject}"

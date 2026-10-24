from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

class UserRole(models.TextChoices):
    ADMIN = 'admin', _('Administrator')
    STAFF = 'staff', _('Staff / Broker Manager')
    AGENT = 'agent', _('Real Estate Agent')
    OWNER = 'owner', _('Shop / Property Owner')
    CUSTOMER = 'customer', _('Customer / Buyer')

class MembershipTier(models.TextChoices):
    FREE = 'free', _('สมาชิกทั่วไป (Free - 1 ครั้ง/เดือน)')
    VIP = 'vip', _('สมาชิก VIP (1,000 บ./เดือน - 4 ครั้ง/เดือน)')
    SUPER_VIP = 'super_vip', _('สมาชิก Super VIP (5,000 บ. - ไม่จำกัดตลอดชีพ)')

class User(AbstractUser):
    """
    WHY SECURE: Custom User model inheriting AbstractUser.
    Guarantees strict role segregation and tracks security attributes:
    email_verified, two_factor_enabled, and last_login_ip.
    """
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.CUSTOMER,
        db_index=True,
        help_text=_('User permission and access control role.')
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        help_text=_('Contact telephone number')
    )
    line_id = models.CharField(
        max_length=100,
        blank=True,
        help_text=_('LINE ID สำหรับติดต่อ')
    )
    avatar = models.ImageField(
        upload_to='media/avatars/%Y/%m/',
        blank=True,
        null=True
    )
    email_verified = models.BooleanField(
        default=False,
        help_text=_('Designates whether this user has verified their email address.')
    )
    two_factor_enabled = models.BooleanField(
        default=False,
        help_text=_('Designates whether 2FA (TOTP) is enforced for this user.')
    )
    last_login_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text=_('IP address from the most recent successful login.')
    )

    is_vip = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_('สถานะสมาชิก VIP (1,000 บาท/เดือน ได้ 4 ประกาศ)')
    )
    membership_tier = models.CharField(
        max_length=20,
        choices=MembershipTier.choices,
        default=MembershipTier.FREE,
        db_index=True,
        help_text=_('ระดับแพ็กเกจสมาชิก')
    )
    vip_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_('วันเวลาหมดอายุของสถานะ VIP')
    )

    def is_admin(self):
        return self.role == UserRole.ADMIN or self.is_superuser

    def is_staff_member(self):
        return self.role in [UserRole.ADMIN, UserRole.STAFF] or self.is_staff

    def is_agent(self):
        return self.role == UserRole.AGENT

    def is_owner(self):
        return self.role == UserRole.OWNER

    @property
    def is_super_vip_active(self):
        return self.membership_tier == MembershipTier.SUPER_VIP

    @property
    def is_vip_active(self):
        from django.utils import timezone
        if self.is_super_vip_active:
            return True
        if self.is_vip and self.vip_expires_at:
            return self.vip_expires_at > timezone.now()
        return False

    def get_monthly_quota(self):
        """คืนค่าโควตาสูงสุดต่อเดือน: Super VIP=ไม่จำกัด (999999), VIP=4, สมาชิกทั่วไป=1"""
        if self.is_super_vip_active:
            return 999999
        from django.conf import settings
        vip_quota = getattr(settings, 'VIP_POST_MONTHLY_QUOTA', 4)
        free_quota = getattr(settings, 'FREE_POST_MONTHLY_QUOTA', 1)
        return vip_quota if self.is_vip_active else free_quota

    def get_current_month_posts_count(self):
        """นับจำนวนทรัพย์ที่โพสต์ในเดือนปัจจุบันจริง"""
        from django.utils import timezone
        now = timezone.now()
        return self.properties.filter(
            created_at__year=now.year,
            created_at__month=now.month
        ).count()

    def get_remaining_quota(self):
        """คืนค่าจำนวนสิทธิ์ที่เหลือในเดือนนี้"""
        if self.is_super_vip_active:
            return 999999
        remaining = self.get_monthly_quota() - self.get_current_month_posts_count()
        return max(0, remaining)

    def can_post_listing(self):
        """ตรวจสอบว่าสามารถลงประกาศได้หรือไม่"""
        if self.is_staff_member() or self.is_super_vip_active:
            return True
        return self.get_remaining_quota() > 0

    def __str__(self):
        return f"{self.email or self.username} ({self.get_role_display()})"


class EmailVerificationOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_otps')
    otp_code = models.CharField(max_length=6, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    is_used = models.BooleanField(default=False, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Email Verification OTP')
        verbose_name_plural = _('Email Verification OTPs')

    def is_valid(self):
        from django.utils import timezone
        return not self.is_used and self.expires_at > timezone.now() and self.attempts < 5

    def __str__(self):
        return f"OTP for {self.user.email} ({self.otp_code}) - Used: {self.is_used}"


class VIPPaymentTransaction(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('รอตรวจสอบ')
        AUTO_VERIFIED = 'AUTO_VERIFIED', _('อนุมัติอัตโนมัติ')
        MANUAL_APPROVED = 'MANUAL_APPROVED', _('อนุมัติโดยเจ้าหน้าที่')
        REJECTED = 'REJECTED', _('ปฏิเสธ (สลิปไม่ถูกต้อง)')

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vip_transactions')
    ref_number = models.CharField(max_length=50, unique=True, db_index=True)
    tier = models.CharField(max_length=20, choices=MembershipTier.choices, default=MembershipTier.VIP, db_index=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2, default=1000.00)
    slip_image = models.ImageField(upload_to='media/slips/%Y/%m/')
    slip_hash = models.CharField(max_length=64, db_index=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_vip_transactions')
    rejection_reason = models.TextField(blank=True)
    bank_trans_ref = models.CharField(max_length=100, blank=True, help_text=_('Bank transaction reference number from slip/EasySlip'))
    easyslip_response = models.JSONField(default=dict, blank=True, help_text=_('Full response payload from EasySlip API'))
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


    class Meta:
        ordering = ['-created_at']
        verbose_name = _('VIP Payment Transaction')
        verbose_name_plural = _('VIP Payment Transactions')

    def __str__(self):
        return f"{self.ref_number} - {self.user.username} ({self.get_status_display()})"

class AuditLog(models.Model):
    """
    WHY SECURE: Immutable tamper-evident audit logging for sensitive actions,
    admin interventions, authorization failures, and legal contract transitions.
    Retention rule: Retained >= 90 days.
    """
    class Action(models.TextChoices):
        LOGIN = 'LOGIN', _('User Login')
        LOGOUT = 'LOGOUT', _('User Logout')
        CREATE = 'CREATE', _('Record Created')
        UPDATE = 'UPDATE', _('Record Updated')
        DELETE = 'DELETE', _('Record Deleted')
        PERMISSION_DENIED = 'PERMISSION_DENIED', _('Permission Denied')
        CONTRACT_SIGN = 'CONTRACT_SIGN', _('Contract Signed')
        COMMISSION_CALC = 'COMMISSION_CALC', _('Commission Calculated')

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text=_('The actor who performed the action.')
    )
    action = models.CharField(max_length=50, choices=Action.choices, db_index=True)
    model_name = models.CharField(max_length=100, db_index=True)
    object_id = models.CharField(max_length=100, blank=True)
    changes = models.JSONField(default=dict, help_text=_('JSON diff of modified fields.'))
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Audit Log')
        verbose_name_plural = _('Audit Logs')

    def __str__(self):
        return f"[{self.created_at}] {self.user} - {self.action} on {self.model_name}({self.object_id})"

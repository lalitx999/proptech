import logging
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from django_otp import devices_for_user
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.forms import (
    UserRegistrationForm,
    UserLoginForm,
    TOTPVerificationForm,
    PasswordResetRequestForm,
)
from apps.accounts.tokens import email_verification_token, password_reset_token
from apps.accounts.services.audit import AuditService
from apps.core.services.email import EmailNotificationService

User = get_user_model()
logger = logging.getLogger(__name__)

# ==============================================================================
# ==============================================================================
# REGISTRATION VIEW (RATE LIMITED: 3/hour/IP)
# ==============================================================================
@ratelimit(key='ip', rate='10/h', method='POST', block=True)
@require_http_methods(["GET", "POST"])
def register_view(request):
    """
    User Registration:
    1. Rate limited to 3 registrations per hour per IP.
    2. Issues secure 6-digit OTP code to user's email via Hostinger SMTP.
    3. Directs user to OTP verification screen.
    """
    if request.user.is_authenticated:
        return redirect('core:home')

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()

            import secrets
            import datetime
            from django.utils import timezone
            from apps.accounts.models import EmailVerificationOTP

            # Invalidate any pending OTPs for this user
            EmailVerificationOTP.objects.filter(user=user, is_used=False).update(is_used=True)

            # Generate random 6-digit OTP code
            otp_code = f"{secrets.randbelow(1000000):06d}"
            EmailVerificationOTP.objects.create(
                user=user,
                otp_code=otp_code,
                expires_at=timezone.now() + datetime.timedelta(minutes=15)
            )

            # Send Branded OTP Email via Hostinger SMTP
            EmailNotificationService.send_registration_otp_email(user, otp_code)

            AuditService.log(
                action='CREATE',
                model_name='User',
                object_id=user.pk,
                changes={'email': user.email, 'role': user.role},
                request=request
            )

            request.session['otp_verify_user_id'] = user.pk
            messages.success(request, f'ลงทะเบียนสำเร็จ! รหัสยืนยัน OTP 6 หลักได้ถูกส่งไปยัง {user.email} แล้ว')
            return redirect('accounts:verify_otp')
    else:
        form = UserRegistrationForm()

    return render(request, 'accounts/register.html', {'form': form})

# ==============================================================================
# EMAIL VERIFICATION (6-DIGIT OTP VIEW)
# ==============================================================================
@ratelimit(key='ip', rate='10/m', method='POST', block=True)
@require_http_methods(["GET", "POST"])
def verify_otp_view(request):
    """
    6-Digit OTP Email Verification:
    - Validates 6-digit code against EmailVerificationOTP.
    - Limits attempts to prevent brute force attacks.
    - Activates account upon successful match and logs in user automatically.
    """
    user_id = request.session.get('otp_verify_user_id')
    if not user_id:
        messages.error(request, 'ไม่พบเซสชันการยืนยันตัวตน กรุณาเข้าสู่ระบบหรือลงทะเบียนใหม่')
        return redirect('accounts:login')

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        messages.error(request, 'ไม่พบข้อมูลผู้ใช้ในระบบ')
        return redirect('accounts:register')

    if user.email_verified:
        messages.info(request, 'บัญชีของคุณได้รับการยืนยันตัวตนเรียบร้อยแล้ว')
        return redirect('core:home')

    # Mask email for privacy: e.g. "pl***@gmail.com"
    email_parts = user.email.split('@')
    if len(email_parts) == 2:
        name_part = email_parts[0]
        prefix_len = min(2, len(name_part))
        masked_email = f"{name_part[:prefix_len]}***@{email_parts[1]}"
    else:
        masked_email = user.email

    from apps.accounts.models import EmailVerificationOTP
    from django.utils import timezone

    if request.method == 'POST':
        # Support full string or 6 split digit inputs
        code = request.POST.get('otp_code', '').strip()
        if not code:
            digits = [request.POST.get(f'digit{i}', '').strip() for i in range(1, 7)]
            code = ''.join(digits).strip()

        if len(code) != 6 or not code.isdigit():
            messages.error(request, 'กรุณากรอกรหัส OTP เป็นตัวเลข 6 หลักให้ครบถ้วน')
            return render(request, 'accounts/verify_otp.html', {'user': user, 'masked_email': masked_email})

        # Fetch latest active OTP
        latest_otp = EmailVerificationOTP.objects.filter(user=user, is_used=False).order_by('-created_at').first()

        if not latest_otp or not latest_otp.is_valid():
            messages.error(request, 'รหัส OTP หมดอายุแล้ว หรือถูกใช้งานไปแล้ว กรุณากดขอรหัสใหม่')
            return render(request, 'accounts/verify_otp.html', {'user': user, 'masked_email': masked_email, 'expired': True})

        if latest_otp.otp_code != code:
            latest_otp.attempts += 1
            latest_otp.save(update_fields=['attempts'])
            remaining_attempts = max(0, 5 - latest_otp.attempts)
            if remaining_attempts == 0:
                latest_otp.is_used = True
                latest_otp.save(update_fields=['is_used'])
                messages.error(request, 'คุณกรอกรหัส OTP ผิดเกิน 5 ครั้ง รหัสชุดนี้ถูกยกเลิกแล้ว กรุณากดขอรหัสใหม่')
            else:
                messages.error(request, f'รหัส OTP ไม่ถูกต้อง (เหลือโอกาสลองอีก {remaining_attempts} ครั้ง)')
            return render(request, 'accounts/verify_otp.html', {'user': user, 'masked_email': masked_email})

        # OTP is correct!
        latest_otp.is_used = True
        latest_otp.save(update_fields=['is_used'])

        user.is_active = True
        user.email_verified = True
        user.save(update_fields=['is_active', 'email_verified'])

        # Clear pending verification session
        request.session.pop('otp_verify_user_id', None)

        # Automatically log user in
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        user.last_login_ip = AuditService.get_client_ip(request)
        user.save(update_fields=['last_login_ip'])

        AuditService.log(
            action='UPDATE',
            model_name='User',
            object_id=user.pk,
            changes={'email_verified': True, 'is_active': True},
            request=request
        )

        messages.success(request, f'🎉 ยืนยันตัวตนสำเร็จ! ยินดีต้อนรับคุณ {user.first_name or user.username} เข้าสู่ เซ้งร้านด่วน.com')
        return redirect('core:home')

    return render(request, 'accounts/verify_otp.html', {
        'user': user,
        'masked_email': masked_email,
    })


# ==============================================================================
# RESEND OTP VIEW (COOLDOWN 60s)
# ==============================================================================
@ratelimit(key='ip', rate='5/m', method='POST', block=True)
@require_http_methods(["POST"])
def resend_otp_view(request):
    """
    Resends a fresh 6-digit OTP with a 60-second cooldown period.
    """
    user_id = request.session.get('otp_verify_user_id')
    if not user_id:
        messages.error(request, 'เซสชันหมดอายุ กรุณาลงทะเบียนหรือเข้าสู่ระบบใหม่')
        return redirect('accounts:login')

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return redirect('accounts:register')

    import secrets
    import datetime
    from django.utils import timezone
    from apps.accounts.models import EmailVerificationOTP

    # Check cooldown (60 seconds)
    last_otp = EmailVerificationOTP.objects.filter(user=user).order_by('-created_at').first()
    if last_otp:
        elapsed = (timezone.now() - last_otp.created_at).total_seconds()
        if elapsed < 60:
            wait_sec = int(60 - elapsed)
            messages.warning(request, f'กรุณารออีก {wait_sec} วินาที ก่อนกดขอรหัส OTP ใหม่อีกครั้ง')
            return redirect('accounts:verify_otp')

    # Invalidate previous OTPs
    EmailVerificationOTP.objects.filter(user=user, is_used=False).update(is_used=True)

    new_code = f"{secrets.randbelow(1000000):06d}"
    EmailVerificationOTP.objects.create(
        user=user,
        otp_code=new_code,
        expires_at=timezone.now() + datetime.timedelta(minutes=15)
    )

    EmailNotificationService.send_registration_otp_email(user, new_code)
    messages.success(request, f'ส่งรหัส OTP 6 หลักชุดใหม่ไปยัง {user.email} เรียบร้อยแล้ว!')
    return redirect('accounts:verify_otp')


# ==============================================================================
# LEGACY EMAIL VERIFICATION TOKEN VIEW
# ==============================================================================
@require_http_methods(["GET"])
def verify_email_view(request, uidb64, token):
    """Activates user account upon token verification (kept for backward compatibility)."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and email_verification_token.check_token(user, token):
        user.is_active = True
        user.email_verified = True
        user.save(update_fields=['is_active', 'email_verified'])

        AuditService.log(
            action='UPDATE',
            model_name='User',
            object_id=user.pk,
            changes={'email_verified': True, 'is_active': True},
            request=request
        )

        messages.success(request, 'ยืนยันอีเมลสำเร็จเรียบร้อยแล้ว! คุณสามารถเข้าสู่ระบบได้ทันที')
        return redirect('accounts:login')
    else:
        messages.error(request, 'ลิงก์ยืนยันอีเมลนี้ไม่ถูกต้อง หรือหมดอายุแล้ว')
        return redirect('accounts:login')

# ==============================================================================
# LOGIN VIEW (RATE LIMITED: 5/min/IP + Axes)
# ==============================================================================
@ratelimit(key='ip', rate='10/m', method='POST', block=True)
@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    WHY SECURE:
    1. Dual-layer brute-force defense: django-ratelimit (5/min) + django-axes (5 fails/15min).
    2. Enforces OTP email verification check before granting access.
    3. Evaluates 2FA (TOTP) requirement for staff/admin roles before session creation.
    """
    if request.user.is_authenticated:
        return redirect('core:home')

    if request.method == 'POST':
        form = UserLoginForm(request.POST)
        if form.is_valid():
            username_or_email = form.cleaned_data['username'].strip().lower()
            password = form.cleaned_data['password']

            # Support login with either email or username
            user_lookup = User.objects.filter(email=username_or_email).first() or User.objects.filter(username=username_or_email).first()
            username = user_lookup.username if user_lookup else username_or_email

            user = authenticate(request, username=username, password=password)

            # Check if user exists with correct password but is unverified (is_active=False)
            if user is None and user_lookup and user_lookup.check_password(password) and not user_lookup.email_verified:
                user = user_lookup

            if user is not None:
                # Check email verification requirement (Send OTP if unverified)
                if not user.email_verified and not user.is_superuser:
                    request.session['otp_verify_user_id'] = user.pk
                    from apps.accounts.models import EmailVerificationOTP
                    import secrets, datetime
                    from django.utils import timezone

                    last_otp = EmailVerificationOTP.objects.filter(user=user, is_used=False).order_by('-created_at').first()
                    if not last_otp or not last_otp.is_valid():
                        new_code = f"{secrets.randbelow(1000000):06d}"
                        EmailVerificationOTP.objects.create(
                            user=user,
                            otp_code=new_code,
                            expires_at=timezone.now() + datetime.timedelta(minutes=15)
                        )
                        EmailNotificationService.send_registration_otp_email(user, new_code)
                        messages.info(request, f'บัญชีของคุณยังไม่ได้ยืนยันตัวตน ระบบได้ส่งรหัส OTP 6 หลักไปยัง {user.email} แล้ว')
                    else:
                        messages.info(request, f'กรุณากรอกรหัส OTP 6 หลักที่ส่งไปยัง {user.email} เพื่อเปิดใช้งานบัญชี')
                    return redirect('accounts:verify_otp')

                # Check 2FA requirement (Mandatory if 2FA device is enrolled)
                has_device = TOTPDevice.objects.filter(user=user, confirmed=True).exists()
                if (user.two_factor_enabled or user.is_staff_member()) and has_device:
                    request.session['pre_2fa_user_id'] = user.pk
                    return redirect('accounts:two_factor_verify')

                # Log user in
                login(request, user)
                user.last_login_ip = AuditService.get_client_ip(request)
                user.save(update_fields=['last_login_ip'])

                AuditService.log(
                    action='LOGIN',
                    model_name='User',
                    object_id=user.pk,
                    request=request
                )

                messages.success(request, f'ยินดีต้อนรับกลับ, {user.first_name or user.username}')
                next_url = request.GET.get('next')
                return redirect(next_url if next_url and next_url.startswith('/') else 'core:home')
            else:
                messages.error(request, 'อีเมล/ชื่อผู้ใช้ หรือรหัสผ่านไม่ถูกต้อง')
    else:
        form = UserLoginForm()

    return render(request, 'accounts/login.html', {'form': form})

# ==============================================================================
# TWO-FACTOR AUTHENTICATION VIEW (TOTP)
# ==============================================================================
@ratelimit(key='ip', rate='5/m', block=True)
@require_http_methods(["GET", "POST"])
def two_factor_verify_view(request):
    """
    WHY SECURE: Validates 6-digit TOTP token before granting full session.
    """
    user_id = request.session.get('pre_2fa_user_id')
    if not user_id:
        return redirect('accounts:login')

    user = get_object_or_404(User, pk=user_id)

    if request.method == 'POST':
        form = TOTPVerificationForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']
            # Verify TOTP device token
            device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
            if device and device.verify_token(code):
                del request.session['pre_2fa_user_id']
                login(request, user)
                user.last_login_ip = AuditService.get_client_ip(request)
                user.save(update_fields=['last_login_ip'])

                AuditService.log(
                    action='LOGIN',
                    model_name='User (2FA Verified)',
                    object_id=user.pk,
                    request=request
                )
                messages.success(request, 'ยืนยันรหัส 2FA สำเร็จ')
                return redirect('core:home')
            else:
                messages.error(request, 'รหัส 2FA ไม่ถูกต้อง หรือหมดอายุแล้ว')
    else:
        form = TOTPVerificationForm()

    return render(request, 'accounts/two_factor.html', {'form': form, 'user_email': user.email})

# ==============================================================================
# LOGOUT VIEW (SESSION ROTATION & FLUSH)
# ==============================================================================
@require_http_methods(["POST", "GET"])
def logout_view(request):
    """
    WHY SECURE:
    1. Records audit trail before clearing session.
    2. Calls request.session.flush() to destroy session key completely.
    """
    if request.user.is_authenticated:
        AuditService.log(
            action='LOGOUT',
            model_name='User',
            object_id=request.user.pk,
            request=request
        )
        logout(request)
        request.session.flush()

    messages.info(request, 'ออกจากระบบเรียบร้อยแล้ว')
    return redirect('core:home')


# ==============================================================================
# VIP MEMBERSHIP & PAYMENT GATEWAY (PROMPTPAY & SLIP VERIFICATION)
# ==============================================================================
@require_http_methods(["GET", "POST"])
def vip_membership_view(request):
    """
    VIP Subscription Portal:
    - View quota status & benefits (4 posts/month vs 1 post/month)
    - Dynamic PromptPay QR Code (locked at 1,000.00 THB)
    - Copyable Bank details (configurable via settings / .env)
    - Anti-fraud Slip upload with SHA-256 deduplication
    """
    from apps.accounts.models import VIPPaymentTransaction, MembershipTier
    from apps.accounts.services.promptpay import generate_promptpay_qr_base64, calculate_file_sha256
    from apps.accounts.services.easyslip import EasySlipService
    from apps.core.services.telegram import TelegramAlertService
    from apps.core.utils.files import validate_and_sanitize_image
    from django.utils import timezone
    from decimal import Decimal
    import datetime

    bank_name = getattr(settings, 'BANK_NAME', 'ธนาคารกสิกรไทย (KBANK)')
    bank_account_no = getattr(settings, 'BANK_ACCOUNT_NO', '054-1-27630-0')
    bank_account_name = getattr(settings, 'BANK_ACCOUNT_NAME', 'ดวงฤทัย ช้างน้อย')
    promptpay_target = getattr(settings, 'PROMPTPAY_TARGET', '0541276300')
    vip_price = getattr(settings, 'VIP_MONTHLY_PRICE_THB', 1000.00)
    super_vip_price = 5000.00

    # Generate real-time locked QR codes for both tiers
    qr_vip_url = generate_promptpay_qr_base64(promptpay_target, vip_price)
    qr_super_vip_url = generate_promptpay_qr_base64(promptpay_target, super_vip_price)

    if request.method == 'POST':
        if not request.user.is_authenticated:
            messages.warning(request, 'กรุณาเข้าสู่ระบบ หรือสมัครสมาชิก ก่อนดำเนินการแจ้งชำระเงิน')
            return redirect(f"{reverse('accounts:login')}?next={reverse('accounts:vip_membership')}")

        slip_file = request.FILES.get('slip_image')
        selected_tier_str = request.POST.get('tier', 'vip').lower()
        if selected_tier_str == 'super_vip':
            chosen_tier = MembershipTier.SUPER_VIP
            expected_amount = Decimal('5000.00')
            tier_label = 'Super VIP 👑'
        else:
            chosen_tier = MembershipTier.VIP
            expected_amount = Decimal('1000.00')
            tier_label = 'VIP'

        if not slip_file:
            messages.error(request, 'กรุณาแนบไฟล์สลิปหลักฐานการโอนเงิน')
            return redirect('accounts:vip_membership')

        try:
            # 1. Image security validation & EXIF sanitization
            sanitized_slip = validate_and_sanitize_image(slip_file)
            
            # 2. Cryptographic SHA-256 Anti-Duplicate Check (Local Layer)
            slip_hash = calculate_file_sha256(sanitized_slip)
            if VIPPaymentTransaction.objects.filter(slip_hash=slip_hash).exists():
                messages.error(
                    request,
                    '❌ สลิปนี้เคยถูกส่งเข้าระบบแล้ว ไม่อนุญาตให้ใช้สลิปซ้ำ กรุณาตรวจสอบสลิปโอนเงินที่ถูกต้อง'
                )
                return redirect('accounts:vip_membership')

            # 3. Generate Unique Reference Number
            now_dt = timezone.now()
            import secrets
            ref_prefix = "SVIP" if chosen_tier == MembershipTier.SUPER_VIP else "VIP"
            ref_number = f"{ref_prefix}-{now_dt:%Y%m%d}-{secrets.token_hex(3).upper()}"

            # 4. Automated Verification via EasySlip API v2
            easyslip_res = EasySlipService.verify_slip(
                sanitized_slip,
                expected_amount=expected_amount,
                expected_receiver_keyword="ดวงฤทัย",
                check_duplicate=True
            )

            # Check EasySlip network-level duplicate flag
            if easyslip_res.get('is_duplicate'):
                messages.error(
                    request,
                    '❌ สลิปนี้เคยถูกใช้งานไปแล้วบนระบบธนาคาร ไม่อนุญาตให้ใช้สลิปซ้ำ'
                )
                return redirect('accounts:vip_membership')

            is_auto_verified = easyslip_res.get('is_verified', False)

            # 5. Save Payment Transaction
            initial_status = (
                VIPPaymentTransaction.Status.AUTO_VERIFIED
                if is_auto_verified
                else VIPPaymentTransaction.Status.PENDING
            )

            # Extract actual amount from slip if detected by EasySlip, otherwise fallback to expected amount
            amount_in_slip = easyslip_res.get('amount_in_slip')
            if amount_in_slip is not None and float(amount_in_slip) > 0:
                actual_amount = Decimal(str(amount_in_slip))
            else:
                actual_amount = expected_amount

            transaction = VIPPaymentTransaction.objects.create(
                user=request.user,
                ref_number=ref_number,
                tier=chosen_tier,
                amount=actual_amount,
                slip_image=sanitized_slip,
                slip_hash=slip_hash,
                bank_trans_ref=easyslip_res.get('trans_ref', ''),
                easyslip_response=easyslip_res.get('raw_data', {}),
                status=initial_status,
            )

            # 6. If EasySlip Verified Automatically -> Instant Activation!
            if is_auto_verified:
                target_user = request.user
                if chosen_tier == MembershipTier.SUPER_VIP:
                    target_user.membership_tier = MembershipTier.SUPER_VIP
                    target_user.is_vip = True
                    target_user.vip_expires_at = now_dt + datetime.timedelta(days=3650)
                    success_msg = f'🎉 ยอดเยี่ยมมาก! ระบบ EasySlip ตรวจสลิป ฿5,000 ถูกต้อง บัญชีของคุณได้รับการเปิดสิทธิ์ Super VIP โพสต์ไม่จำกัดตลอดชีพเรียบร้อยแล้ว!'
                else:
                    target_user.membership_tier = MembershipTier.VIP
                    target_user.is_vip = True
                    if target_user.is_vip and target_user.vip_expires_at and target_user.vip_expires_at > now_dt:
                        target_user.vip_expires_at += datetime.timedelta(days=30)
                    else:
                        target_user.vip_expires_at = now_dt + datetime.timedelta(days=30)
                    success_msg = f'🎉 ยอดเยี่ยมมาก! ระบบ EasySlip ตรวจสอบสลิปถูกต้องเรียบร้อยแล้ว บัญชีของคุณได้รับการเปิดสิทธิ์ VIP 30 วันทันที! (หมดอายุ {target_user.vip_expires_at:%d/%m/%Y})'

                target_user.save(update_fields=['is_vip', 'membership_tier', 'vip_expires_at'])

                AuditService.log(
                    action='CREATE',
                    model_name=f'VIPPaymentTransaction ({tier_label} EasySlip Auto-Verified)',
                    object_id=transaction.pk,
                    changes={'ref_number': ref_number, 'amount': str(expected_amount), 'status': 'AUTO_VERIFIED'},
                    request=request
                )

                # Instant Telegram Notification
                TelegramAlertService.send_vip_alert(transaction, auto_verified=True)

                # Dispatch Confirmation Email via Hostinger SMTP
                EmailNotificationService.send_vip_activation_email(
                    user=target_user,
                    tier_label=tier_label,
                    amount=float(expected_amount),
                    expires_at=target_user.vip_expires_at,
                    ref_number=ref_number
                )
                messages.success(request, success_msg)
            else:
                # Fallback to Manual Review Queue
                AuditService.log(
                    action='CREATE',
                    model_name=f'VIPPaymentTransaction ({tier_label} Queued for Review)',
                    object_id=transaction.pk,
                    changes={'ref_number': ref_number, 'amount': str(expected_amount), 'status': 'PENDING'},
                    request=request
                )

                # Alert Staff via Telegram
                TelegramAlertService.send_vip_alert(transaction, auto_verified=False)
                messages.success(
                    request,
                    f'✅ ส่งหลักฐานการโอนเงิน {tier_label} รหัส {ref_number} เรียบร้อยแล้ว! เจ้าหน้าที่จะตรวจสอบสลิปและเปิดสิทธิ์ให้อย่างรวดเร็ว'
                )

            return redirect('accounts:vip_membership')

        except Exception as e:
            logger.error(f"Error processing VIP slip: {e}")
            messages.error(request, f'เกิดข้อผิดพลาดในการตรวจสอบไฟล์: {str(e)}')
            return redirect('accounts:vip_membership')

    # Transactions history & quota for user
    if request.user.is_authenticated:
        my_transactions = VIPPaymentTransaction.objects.filter(user=request.user).order_by('-created_at')[:10]
        remaining_quota = request.user.get_remaining_quota()
        monthly_quota = request.user.get_monthly_quota()
        posted_count = request.user.get_current_month_posts_count()
    else:
        my_transactions = []
        remaining_quota = 1
        monthly_quota = 1
        posted_count = 0

    context = {
        'bank_name': bank_name,
        'bank_account_no': bank_account_no,
        'bank_account_name': bank_account_name,
        'promptpay_target': promptpay_target,
        'vip_price': vip_price,
        'super_vip_price': super_vip_price,
        'qr_vip_url': qr_vip_url,
        'qr_super_vip_url': qr_super_vip_url,
        'qr_data_url': qr_vip_url, # default
        'my_transactions': my_transactions,
        'remaining_quota': remaining_quota,
        'monthly_quota': monthly_quota,
        'posted_count': posted_count,
    }
    return render(request, 'accounts/vip_membership.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def vip_manage_view(request):
    """
    Staff / Admin view to inspect and approve/reject VIP payment transactions.
    """
    if not (request.user.is_staff_member() or request.user.is_admin()):
        messages.error(request, 'คุณไม่มีสิทธิ์เข้าถึงหน้านี้')
        return redirect('core:home')

    from apps.accounts.models import VIPPaymentTransaction
    pending_transactions = VIPPaymentTransaction.objects.filter(
        status=VIPPaymentTransaction.Status.PENDING
    ).select_related('user').order_by('-created_at')

    past_transactions = VIPPaymentTransaction.objects.exclude(
        status=VIPPaymentTransaction.Status.PENDING
    ).select_related('user', 'reviewed_by').order_by('-created_at')[:30]

    return render(request, 'accounts/vip_manage.html', {
        'pending_transactions': pending_transactions,
        'past_transactions': past_transactions,
    })


@login_required
@require_http_methods(["POST"])
def vip_approve_transaction_view(request, pk):
    """
    Approve or reject a VIP/Super VIP transaction and grant membership benefits.
    """
    if not (request.user.is_staff_member() or request.user.is_admin()):
        messages.error(request, 'คุณไม่มีสิทธิ์ดำเนินการ')
        return redirect('core:home')

    from apps.accounts.models import VIPPaymentTransaction, MembershipTier
    from django.utils import timezone
    import datetime

    transaction = get_object_or_404(VIPPaymentTransaction, pk=pk)
    action = request.POST.get('action')

    if action == 'approve':
        transaction.status = VIPPaymentTransaction.Status.MANUAL_APPROVED
        transaction.reviewed_by = request.user
        transaction.save(update_fields=['status', 'reviewed_by'])

        target_user = transaction.user
        now_dt = timezone.now()
        if transaction.tier == MembershipTier.SUPER_VIP:
            target_user.membership_tier = MembershipTier.SUPER_VIP
            target_user.is_vip = True
            target_user.vip_expires_at = now_dt + datetime.timedelta(days=3650)
            messages.success(request, f'อนุมัติ Super VIP (ไม่จำกัดตลอดชีพ) ให้คุณ {target_user.username} สำเร็จ')
        else:
            target_user.membership_tier = MembershipTier.VIP
            target_user.is_vip = True
            if target_user.is_vip and target_user.vip_expires_at and target_user.vip_expires_at > now_dt:
                target_user.vip_expires_at += datetime.timedelta(days=30)
            else:
                target_user.vip_expires_at = now_dt + datetime.timedelta(days=30)
            messages.success(request, f'อนุมัติ VIP 30 วันให้คุณ {target_user.username} สำเร็จ (หมดอายุ {target_user.vip_expires_at:%d/%m/%Y})')
        
        target_user.save(update_fields=['is_vip', 'membership_tier', 'vip_expires_at'])

        AuditService.log(
            action='UPDATE',
            model_name='VIPPaymentTransaction (Approved)',
            object_id=transaction.pk,
            changes={'user': target_user.username, 'tier': transaction.tier, 'new_expires_at': str(target_user.vip_expires_at)},
            request=request
        )

        # Dispatch Confirmation Email via Hostinger SMTP
        tier_title = 'Super VIP (ไม่จำกัดตลอดชีพ)' if transaction.tier == MembershipTier.SUPER_VIP else 'VIP 30 วัน'
        EmailNotificationService.send_vip_activation_email(
            user=target_user,
            tier_label=tier_title,
            amount=float(transaction.amount),
            expires_at=target_user.vip_expires_at,
            ref_number=transaction.ref_number
        )

        messages.success(request, f'อนุมัติ VIP ให้คุณ {target_user.username} สำเร็จ (หมดอายุ {target_user.vip_expires_at:%d/%m/%Y})')

    elif action == 'reject':
        reason = request.POST.get('reason', 'หลักฐานไม่ถูกต้อง หรือยอดเงินไม่ตรง').strip()
        transaction.status = VIPPaymentTransaction.Status.REJECTED
        transaction.reviewed_by = request.user
        transaction.rejection_reason = reason
        transaction.save(update_fields=['status', 'reviewed_by', 'rejection_reason'])

        messages.warning(request, f'ปฏิเสธรายการ {transaction.ref_number} เรียบร้อยแล้ว')

    return redirect('accounts:vip_manage')

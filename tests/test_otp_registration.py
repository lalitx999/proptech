from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
import datetime

from apps.accounts.models import UserRole, EmailVerificationOTP

User = get_user_model()


class OTPRegistrationAndVerificationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.register_url = reverse('accounts:register')
        self.verify_otp_url = reverse('accounts:verify_otp')
        self.resend_otp_url = reverse('accounts:resend_otp')
        self.login_url = reverse('accounts:login')

    def test_registration_creates_user_and_otp(self):
        """User registration creates account, issues 6-digit OTP and redirects to verify_otp."""
        payload = {
            'email': 'newuser@example.com',
            'first_name': 'Somchai',
            'last_name': 'Dee',
            'phone': '0812345678',
            'role': UserRole.CUSTOMER,
            'password': 'SecurePassword123!',
            'password_confirm': 'SecurePassword123!',
            'website': '',
        }
        res = self.client.post(self.register_url, payload, follow=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, self.verify_otp_url)

        user = User.objects.filter(email='newuser@example.com').first()
        self.assertIsNotNone(user)
        self.assertFalse(user.email_verified)
        self.assertFalse(user.is_active)

        # Check OTP created
        otp = EmailVerificationOTP.objects.filter(user=user, is_used=False).first()
        self.assertIsNotNone(otp)
        self.assertEqual(len(otp.otp_code), 6)
        self.assertTrue(otp.otp_code.isdigit())
        self.assertTrue(otp.is_valid())

    def test_verify_valid_otp_activates_user_and_logs_in(self):
        """Entering correct 6-digit OTP activates user and logs them in."""
        user = User.objects.create_user(
            username='otpuser@example.com',
            email='otpuser@example.com',
            password='SecurePassword123!',
            is_active=False,
            email_verified=False,
        )
        otp = EmailVerificationOTP.objects.create(
            user=user,
            otp_code='849201',
            expires_at=timezone.now() + datetime.timedelta(minutes=15)
        )

        session = self.client.session
        session['otp_verify_user_id'] = user.pk
        session.save()

        res = self.client.post(self.verify_otp_url, {'otp_code': '849201'}, follow=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, reverse('core:home'))

        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.email_verified)

        otp.refresh_from_db()
        self.assertTrue(otp.is_used)

        # Verify logged in
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_verify_invalid_otp_fails_and_increments_attempts(self):
        """Invalid OTP rejects and records wrong attempts."""
        user = User.objects.create_user(
            username='wrongotp@example.com',
            email='wrongotp@example.com',
            password='SecurePassword123!',
            is_active=False,
            email_verified=False,
        )
        otp = EmailVerificationOTP.objects.create(
            user=user,
            otp_code='112233',
            expires_at=timezone.now() + datetime.timedelta(minutes=15)
        )

        session = self.client.session
        session['otp_verify_user_id'] = user.pk
        session.save()

        res = self.client.post(self.verify_otp_url, {'otp_code': '999999'}, follow=True)
        self.assertEqual(res.status_code, 200)

        otp.refresh_from_db()
        self.assertEqual(otp.attempts, 1)
        self.assertFalse(otp.is_used)

        user.refresh_from_db()
        self.assertFalse(user.email_verified)

    def test_resend_otp_creates_new_code_after_cooldown(self):
        """Resend OTP issues a new code when cooldown period has passed."""
        user = User.objects.create_user(
            username='resend@example.com',
            email='resend@example.com',
            password='SecurePassword123!',
            is_active=False,
            email_verified=False,
        )
        old_otp = EmailVerificationOTP.objects.create(
            user=user,
            otp_code='111111',
            expires_at=timezone.now() + datetime.timedelta(minutes=10)
        )
        EmailVerificationOTP.objects.filter(pk=old_otp.pk).update(
            created_at=timezone.now() - datetime.timedelta(seconds=70)
        )

        session = self.client.session
        session['otp_verify_user_id'] = user.pk
        session.save()

        res = self.client.post(self.resend_otp_url, follow=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, self.verify_otp_url)

        old_otp.refresh_from_db()
        self.assertTrue(old_otp.is_used)

        new_otp = EmailVerificationOTP.objects.filter(user=user, is_used=False).order_by('-created_at').first()
        self.assertIsNotNone(new_otp)
        self.assertNotEqual(new_otp.otp_code, '111111')

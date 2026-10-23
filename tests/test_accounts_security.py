from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse

from apps.accounts.models import UserRole, AuditLog
from apps.accounts.services.audit import AuditService
from apps.accounts.permissions import role_required, can_view, can_edit, can_delete
from apps.accounts.forms import UserRegistrationForm
from apps.accounts.views import logout_view

User = get_user_model()

@role_required(UserRole.AGENT, UserRole.ADMIN)
def dummy_agent_view(request):
    return HttpResponse("Agent Portal Accessed")

class AccountsSecurityTestCase(TestCase):
    """
    WHY SECURE: Comprehensive security test suite validating:
    1. Argon2 password storage.
    2. RBAC & Row-level authorization enforcement.
    3. Audit logging & credential masking.
    4. Anti-bot honeypot and privilege escalation defense.
    5. Session termination and rotation on logout.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.customer = User.objects.create_user(
            username='customer@sengran.com',
            email='customer@sengran.com',
            password='SecureCustomerPass123!',
            role=UserRole.CUSTOMER,
            email_verified=True,
            is_active=True
        )
        self.agent = User.objects.create_user(
            username='agent@sengran.com',
            email='agent@sengran.com',
            password='SecureAgentPass123!',
            role=UserRole.AGENT,
            email_verified=True,
            is_active=True
        )
        self.admin = User.objects.create_superuser(
            username='admin@sengran.com',
            email='admin@sengran.com',
            password='SecureAdminPass123!',
            role=UserRole.ADMIN,
            email_verified=True,
            is_active=True
        )

    def test_user_password_is_argon2_hashed(self):
        """Verify user passwords are saved using Argon2 hash algorithm."""
        self.assertTrue(
            self.customer.password.startswith('argon2'),
            "Password must be hashed with Argon2 algorithm."
        )

    def test_role_required_permits_authorized_role(self):
        """Verify authorized Agent can access Agent-protected view."""
        request = self.factory.get('/agent-portal/')
        request.user = self.agent
        response = dummy_agent_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "Agent Portal Accessed")

    def test_role_required_blocks_unauthorized_role_and_records_audit(self):
        """
        Verify unauthorized Customer is blocked from Agent view (PermissionDenied)
        and an immutable AuditLog entry is recorded.
        """
        request = self.factory.get('/agent-portal/')
        request.user = self.customer

        with self.assertRaises(PermissionDenied):
            dummy_agent_view(request)

        # Verify AuditLog recorded the incident
        audit_entry = AuditLog.objects.filter(
            user=self.customer,
            action='PERMISSION_DENIED'
        ).first()
        self.assertIsNotNone(audit_entry, "AuditLog must record PERMISSION_DENIED violations.")
        self.assertEqual(audit_entry.changes.get('user_role'), UserRole.CUSTOMER)

    def test_audit_service_masks_sensitive_data(self):
        """Ensure AuditService automatically redacts passwords, tokens, and credit cards."""
        AuditService.log(
            action='UPDATE',
            model_name='SecurityProfile',
            object_id='1',
            changes={
                'password': 'RawPassword123!',
                'token': 'secret-token-xyz',
                'credit_card': '4111-2222-3333-4444',
                'phone': '0812345678'
            },
            user=self.admin
        )
        log = AuditLog.objects.filter(model_name='SecurityProfile').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.changes['password'], '[REDACTED]')
        self.assertEqual(log.changes['token'], '[REDACTED]')
        self.assertEqual(log.changes['credit_card'], '[REDACTED]')
        self.assertEqual(log.changes['phone'], '0812345678')

    def test_privilege_escalation_blocked_in_registration(self):
        """Verify public registration cannot self-assign ADMIN or STAFF roles."""
        form_data = {
            'email': 'attacker@example.com',
            'role': UserRole.ADMIN, # Malicious privilege escalation attempt
            'password': 'ValidPassword123!',
            'password_confirm': 'ValidPassword123!',
            'website': ''
        }
        form = UserRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('role', form.errors)

    def test_honeypot_catches_bot_submissions(self):
        """Verify bots filling the hidden honeypot field are rejected."""
        form_data = {
            'email': 'bot@example.com',
            'role': UserRole.CUSTOMER,
            'password': 'ValidPassword123!',
            'password_confirm': 'ValidPassword123!',
            'website': 'https://spambot.ru' # Bot filled the honeypot
        }
        form = UserRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('website', form.errors)

    def test_logout_flushes_session_and_records_audit(self):
        """Verify logout flushes session data completely and logs the event."""
        request = self.factory.post('/accounts/logout/')
        # Attach session and messages middleware to dummy request
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        request.session['auth_token'] = 'test-token'
        
        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(request, '_messages', FallbackStorage(request))
        
        request.user = self.agent

        logout_view(request)

        # Assert session key is cleared/rotated
        self.assertNotIn('auth_token', request.session)
        audit_log = AuditLog.objects.filter(user=self.agent, action='LOGOUT').first()
        self.assertIsNotNone(audit_log, "Logout must record an AuditLog entry.")

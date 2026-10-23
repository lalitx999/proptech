import os
import unittest
from django.conf import settings
from django.test import SimpleTestCase

class SecuritySettingsTestCase(SimpleTestCase):
    databases = {'default'}
    """
    WHY SECURE: Automated regression testing of the system's security baseline.
    Ensures no developer accidentally loosens session, password, or CSP settings.
    """

    def test_password_hasher_argon2_is_primary(self):
        """Ensure Argon2 is configured as the first and primary password hasher."""
        primary_hasher = settings.PASSWORD_HASHERS[0]
        self.assertEqual(
            primary_hasher,
            'django.contrib.auth.hashers.Argon2PasswordHasher',
            "Primary password hasher MUST be Argon2 to resist GPU cracking attacks."
        )

    def test_session_cookie_hardening(self):
        """Verify session cookie cannot be read via JavaScript and has Lax samesite."""
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY, "SESSION_COOKIE_HTTPONLY must be True to prevent XSS session theft.")
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, 'Lax', "SESSION_COOKIE_SAMESITE must be Lax to defend against CSRF.")
        self.assertEqual(settings.SESSION_COOKIE_AGE, 43200, "Absolute session lifetime must be 12 hours (43200 seconds).")

    def test_csrf_cookie_hardening(self):
        """Verify CSRF cookie flags."""
        self.assertTrue(settings.CSRF_COOKIE_HTTPONLY, "CSRF_COOKIE_HTTPONLY must be True.")
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, 'Lax', "CSRF_COOKIE_SAMESITE must be Lax.")

    def test_clickjacking_defense(self):
        """Verify X-Frame-Options is DENY."""
        self.assertEqual(settings.X_FRAME_OPTIONS, 'DENY', "X_FRAME_OPTIONS must be DENY to prevent clickjacking.")

    def test_axes_brute_force_parameters(self):
        """Verify login throttling allows max 5 failed attempts within 15 minutes."""
        self.assertEqual(settings.AXES_FAILURE_LIMIT, 5, "Axes must lockout after 5 failed attempts.")
        self.assertEqual(settings.AXES_COOLOFF_TIME.total_seconds(), 900, "Axes lockout duration must be 15 minutes (900 seconds).")

    def test_content_security_policy_framing(self):
        """Verify CSP denies framing."""
        self.assertEqual(settings.CSP_FRAME_ANCESTORS, ("'none'",), "CSP frame-ancestors must be 'none'.")

    def test_healthz_endpoint_status(self):
        """Verify /healthz returns 200 OK and database connectivity status."""
        response = self.client.get('/healthz')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "db": "ok"})

    def test_client_ip_resolver(self):
        """Verify get_client_ip prioritizes HTTP_X_REAL_IP over REMOTE_ADDR."""
        from apps.core.client_ip import get_client_ip
        from django.test import RequestFactory
        factory = RequestFactory()

        # Case 1: X-Real-IP provided by Nginx from Cloudflare CF-Connecting-IP
        req1 = factory.get('/', HTTP_X_REAL_IP='203.0.113.195', REMOTE_ADDR='172.18.0.3')
        self.assertEqual(get_client_ip(req1), '203.0.113.195')

        # Case 2: Direct connection fallback
        req2 = factory.get('/', REMOTE_ADDR='198.51.100.4')
        self.assertEqual(get_client_ip(req2), '198.51.100.4')

    def test_axes_ipware_and_lockout_configuration(self):
        """Verify Axes locks out per (user, IP) tuple and inspects real IP header."""
        self.assertEqual(settings.AXES_LOCKOUT_PARAMETERS, [['username', 'ip_address']])
        self.assertEqual(settings.AXES_IPWARE_META_PRECEDENCE_ORDER, ['HTTP_X_REAL_IP', 'REMOTE_ADDR'])
        self.assertEqual(settings.RATELIMIT_IP_META_KEY, 'apps.core.client_ip.get_client_ip')

    def test_production_settings_enforcement(self):
        """
        Verify that under config.settings.prod:
        1. DEBUG is False
        2. HSTS is 1 year (31536000)
        3. SSL Redirect is True
        4. Cookies are Secure
        5. django.contrib.admin is NOT installed
        """
        old_env = os.environ.copy()
        try:
            # Set dummy env vars to allow importing prod settings cleanly
            os.environ['SECRET_KEY'] = 'test-secret-key-at-least-fifty-characters-long-for-testing'
            os.environ['ALLOWED_HOSTS'] = 'sengran.com,www.sengran.com'
            os.environ['CSRF_TRUSTED_ORIGINS'] = 'https://sengran.com'
            os.environ['DB_NAME'] = 'test_db'
            os.environ['DB_USER'] = 'test_user'
            os.environ['DB_PASSWORD'] = 'test_pass'
            os.environ['DB_HOST'] = 'localhost'
            # HSTS is env-driven (low default for a brand-new domain); verify full values are honored
            os.environ['SECURE_HSTS_SECONDS'] = '31536000'
            os.environ['SECURE_HSTS_PRELOAD'] = 'True'

            import importlib
            from config.settings import prod
            importlib.reload(prod)

            self.assertFalse(prod.DEBUG, "DEBUG must be strictly False in production.")
            self.assertTrue(prod.SECURE_SSL_REDIRECT, "SECURE_SSL_REDIRECT must be True in production.")
            self.assertEqual(prod.SECURE_HSTS_SECONDS, 31536000, "Configured HSTS duration must be honored.")
            self.assertTrue(prod.SECURE_HSTS_PRELOAD, "Configured HSTS preload must be honored.")
            self.assertEqual(prod.SECURE_PROXY_SSL_HEADER, ('HTTP_X_FORWARDED_PROTO', 'https'))
            self.assertTrue(prod.DATABASES['default']['CONN_HEALTH_CHECKS'])
            self.assertTrue(prod.SESSION_COOKIE_SECURE, "SESSION_COOKIE_SECURE must be True in production.")
            self.assertTrue(prod.CSRF_COOKIE_SECURE, "CSRF_COOKIE_SECURE must be True in production.")
            self.assertNotIn(
                'django.contrib.admin',
                prod.INSTALLED_APPS,
                "django.contrib.admin must NEVER be in INSTALLED_APPS in production."
            )
        finally:
            os.environ.clear()
            os.environ.update(old_env)

if __name__ == '__main__':
    unittest.main()

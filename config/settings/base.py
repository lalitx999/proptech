import datetime
import os
from pathlib import Path
from decouple import Csv, config

# ==============================================================================
# BASE DIRECTORY DEFINITION
# ==============================================================================
# Points to the proptech/ root
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ==============================================================================
# CORE SECURITY SETTINGS
# ==============================================================================
# WHY SECURE: Secret key is never hardcoded. Loaded from environment or encrypted secret store.
# ⚠️ WARNING: If SECRET_KEY is leaked, attackers can forge session cookies and tamper with CSRF tokens.
SECRET_KEY = config('SECRET_KEY')

# Application definition
INSTALLED_APPS = [
    # Core Django Components
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    
    # Security & Authentication Frameworks
    'django.contrib.auth',
    'axes',                      # Brute-force login defense
    'django_otp',                # Two-Factor Authentication Core
    'django_otp.plugins.otp_totp', # TOTP (Google Authenticator / Authy)
    'csp',                       # Content Security Policy Engine

    # Local Domain Apps
    'apps.accounts.apps.AccountsConfig',
    'apps.properties.apps.PropertiesConfig',
    'apps.listings.apps.ListingsConfig',
    'apps.leads.apps.LeadsConfig',
    'apps.contracts.apps.ContractsConfig',
    'apps.core.apps.CoreConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'apps.core.middleware.LegacyWordpressRedirectMiddleware', # SEO 301 preservation for WordPress links
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django_otp.middleware.OTPMiddleware',           # 2FA state evaluation
    'apps.accounts.middleware.SessionIdleTimeoutMiddleware', # Enforces 30-min idle timeout
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'csp.middleware.CSPMiddleware',                   # Injects strict CSP headers
    'axes.middleware.AxesMiddleware',                 # Must be near bottom of middleware stack
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'csp.context_processors.nonce',      # Allows {% csp_nonce %} in templates
                'apps.core.context_processors.site_url',  # {{ site_url }} for canonical/schema/OG URLs
            ],
            # WHY SECURE: autoescape defaults to True. Never set to False globally.
            'autoescape': True,
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ==============================================================================
# AUTHENTICATION & PASSWORD STORAGE
# ==============================================================================
# Custom User Model
AUTH_USER_MODEL = 'accounts.User'

# WHY SECURE: Argon2 is the winner of the Password Hashing Competition (PHC).
# It resists GPU/ASIC cracking far better than standard PBKDF2.
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
]

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',  # Evaluates failed attempts before standard auth
    'django.contrib.auth.backends.ModelBackend',
]

# Strict Password Validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 10}, # Enforce >= 10 characters minimum
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# ==============================================================================
# SESSION HARDENING
# ==============================================================================
# WHY SECURE: HttpOnly prevents JavaScript from reading session ID (Mitigates Session Hijacking via XSS)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
# Absolute session expiration: 12 hours
SESSION_COOKIE_AGE = 43200
# Idle session expiration: 30 minutes (evaluated by SessionIdleTimeoutMiddleware)
SESSION_IDLE_TIMEOUT_SECONDS = 1800
SESSION_SAVE_EVERY_REQUEST = True

# ==============================================================================
# CSRF HARDENING
# ==============================================================================
# WHY SECURE: HttpOnly=True on CSRF cookie ensures token cannot be stolen via JS injection.
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

# ==============================================================================
# AXES (LOGIN BRUTE-FORCE DEFENSE)
# ==============================================================================
AXES_FAILURE_LIMIT = 5                      # Lock out after 5 consecutive failed attempts
AXES_COOLOFF_TIME = datetime.timedelta(minutes=15) # 15-minute lockout period
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = 'accounts/lockout.html'
AXES_ENABLE_ACCESS_FAILURE_LOG = True       # Record audit entries on attacks

# WHY CRITICAL (Cloudflare Tunnel): every request reaches Django from the nginx container,
# so REMOTE_ADDR is identical for all users. Nginx resolves the real client IP from
# CF-Connecting-IP (trusted only from the docker network) and always OVERWRITES X-Real-IP,
# so clients cannot spoof it. Lock out the (username, IP) pair, never the IP alone,
# so one attacker cannot lock every user out of the site.
AXES_IPWARE_META_PRECEDENCE_ORDER = ['HTTP_X_REAL_IP', 'REMOTE_ADDR']
AXES_LOCKOUT_PARAMETERS = [['username', 'ip_address']]

# django-ratelimit key='ip' uses this resolver (same trust model as above; falls back
# to REMOTE_ADDR so direct/internal requests never raise ImproperlyConfigured)
RATELIMIT_IP_META_KEY = 'apps.core.client_ip.get_client_ip'

# ==============================================================================
# CACHE (shared across gunicorn workers so rate-limit counters are global)
# ==============================================================================
# DatabaseCache avoids adding Redis at current scale (<10 req/s).
# Requires: python manage.py createcachetable (run by entrypoint.sh)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'django_cache',
        'TIMEOUT': 300,
    }
}

# ==============================================================================
# CONTENT SECURITY POLICY (CSP)
# ==============================================================================
# WHY SECURE: Restricts resource loading to prevent XSS and data exfiltration.
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "https://cdn.tailwindcss.com", "https://unpkg.com", "https://cdn.jsdelivr.net")
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "https://fonts.googleapis.com", "https://unpkg.com")
CSP_IMG_SRC = ("'self'", "data:", "https:")
CSP_FONT_SRC = ("'self'", "https:", "data:", "https://fonts.gstatic.com")
CSP_FRAME_ANCESTORS = ("'none'",)
CSP_INCLUDE_NONCE_IN = ['script-src']

# HTTP Security Headers
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# ==============================================================================
# INTERNATIONALIZATION
# ==============================================================================
LANGUAGE_CODE = 'th'
TIME_ZONE = 'Asia/Bangkok'
USE_I18N = True
USE_TZ = True

# ==============================================================================
# STATIC & MEDIA FILES
# ==============================================================================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# File Upload Thresholds (Denial of Service Mitigation)
# ⚠️ Limit in-memory buffering to 10MB to prevent memory exhaustion DoS
DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760 # 10MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760 # 10MB

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ==============================================================================
# VIP MEMBERSHIP & PAYMENT GATEWAY SETTINGS
# ==============================================================================
VIP_MONTHLY_PRICE_THB = 1000.00
VIP_POST_MONTHLY_QUOTA = 4
FREE_POST_MONTHLY_QUOTA = 1

# Bank Transfer & PromptPay Configuration (Configurable via .env)
# WHY SECURE: No real account data as code defaults - must be provided via .env
BANK_NAME = config('BANK_NAME', default='')
BANK_ACCOUNT_NO = config('BANK_ACCOUNT_NO', default='')
BANK_ACCOUNT_NAME = config('BANK_ACCOUNT_NAME', default='')
BANK_CODE = config('BANK_CODE', default='KBANK')
PROMPTPAY_TARGET = config('PROMPTPAY_TARGET', default='')

# EasySlip Slip Verification Gateway (API v2)
EASYSLIP_API_KEY = config('EASYSLIP_API_KEY', default='')
EASYSLIP_API_URL = config('EASYSLIP_API_URL', default='https://api.easyslip.com/v2')

# Telegram Bot Notification Settings
TELEGRAM_BOT_TOKEN = config('TELEGRAM_BOT_TOKEN', default='')
TELEGRAM_CHAT_ID = config('TELEGRAM_CHAT_ID', default='')

# ==============================================================================
# EMAIL CONFIGURATION (HOSTINGER SMTP)
# ==============================================================================
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.hostinger.com')
EMAIL_PORT = config('EMAIL_PORT', default=465, cast=int)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=True, cast=bool)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=False, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='เซ้งร้านด่วน.com <no-reply@localhost>')
SERVER_EMAIL = DEFAULT_FROM_EMAIL
# WHY CRITICAL: OTP mail is sent synchronously inside the request. Without a timeout a
# slow/unreachable SMTP server blocks a gunicorn worker indefinitely.
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=10, cast=int)

# ==============================================================================
# PUBLIC SITE URL (canonical, sitemap, schema.org, OpenGraph, llms.txt)
# ==============================================================================
SITE_URL = config('SITE_URL', default='https://sengranduan.com').rstrip('/')


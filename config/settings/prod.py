import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from decouple import Csv, config
from .base import *

# ==============================================================================
# PRODUCTION SECURITY ENFORCEMENT
# ==============================================================================
# ⚠️ STRICT REQUIREMENT: DEBUG must always be False in production
DEBUG = False

ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', cast=Csv())

# Zero-Admin on Production enforcement
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'django.contrib.admin']

# Database Configuration with Persistent Connections
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 600, # Reuse connection for 10 minutes (reduces connection overhead)
        'CONN_HEALTH_CHECKS': True, # Discard stale persistent connections (e.g. after DB restart)
    }
}

# ==============================================================================
# STRICT HTTPS & TRANSPORT SECURITY
# ==============================================================================
# WHY SECURE: Enforces browser to communicate over TLS 1.2+ only
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# Internal docker healthcheck calls the app directly over http (no proxy headers)
SECURE_REDIRECT_EXEMPT = [r'^healthz$']

# HTTP Strict Transport Security (HSTS)
# ⚠️ Start low on a brand-new domain: a wrong HSTS/preload setting is very hard to undo.
# Raise to 31536000 and enable PRELOAD after the site has run cleanly on HTTPS for a while.
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=3600, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False, cast=bool)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=False, cast=bool)

# Cookies over HTTPS only
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# ==============================================================================
# SENTRY ERROR TRACKING (WITH PII SANITIZATION)
# ==============================================================================
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    def strip_sensitive_data(event, hint):
        """
        WHY SECURE: Strips sensitive PII, passwords, credit card numbers,
        and tokens before sending crash reports to Sentry.
        """
        if 'request' in event:
            headers = event['request'].get('headers', {})
            for sensitive_key in ['Authorization', 'Cookie', 'X-CSRFToken']:
                if sensitive_key in headers:
                    headers[sensitive_key] = '[REDACTED]'
            if 'data' in event['request'] and isinstance(event['request']['data'], dict):
                for k in list(event['request']['data'].keys()):
                    if any(term in k.lower() for term in ['password', 'token', 'secret', 'card', 'id_card']):
                        event['request']['data'][k] = '[REDACTED]'
        return event

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.05,
        send_default_pii=False,
        before_send=strip_sensitive_data,
    )

# ==============================================================================
# LOGGING CONFIGURATION
# ==============================================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} [{name}:{lineno}] {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'proptech.log',
            'maxBytes': 10485760, # 10 MB per log file
            'backupCount': 10,
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'WARNING',
    },
    'loggers': {
        'django.security': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'axes': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

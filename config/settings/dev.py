from .base import *
from decouple import Csv, config

# ==============================================================================
# DEVELOPMENT SETTINGS
# ==============================================================================
DEBUG = True

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='127.0.0.1,localhost,testserver', cast=Csv())

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='proptech_db'),
        'USER': config('DB_USER', default='proptech_user'),
        'PASSWORD': config('DB_PASSWORD', default='proptech_secure_password_replace_in_prod'),
        'HOST': config('DB_HOST', default='127.0.0.1'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

# In local dev without HTTPS, cookies cannot be SECURE
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

EMAIL_BACKEND = config('EMAIL_BACKEND', default=EMAIL_BACKEND)

# Optional Dev-Only Admin for inspection during initial local scaffolding
# ⚠️ WHY SECURE: Create a new list copy to prevent mutating base.INSTALLED_APPS in memory!
INSTALLED_APPS = list(INSTALLED_APPS) + ['django.contrib.admin']

# Disable rate limiting in local development to prevent blocking localhost
RATELIMIT_ENABLE = False

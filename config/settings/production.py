"""
GymForge — Production Settings (Railway single-tenant deploy)
"""
from .base import *
import os

DEBUG = os.environ.get('DJANGO_DEBUG', '') == 'True'

ALLOWED_HOSTS = [
    '.railway.app',
    os.environ.get('RAILWAY_PUBLIC_DOMAIN', ''),
    os.environ.get('CUSTOM_DOMAIN', ''),  # e.g. app.ironhousegym.com
]
# Filter out empty strings
ALLOWED_HOSTS = [h for h in ALLOWED_HOSTS if h]

# ---------------------------------------------------------------------------
# File Storage — Cloudflare R2
# ---------------------------------------------------------------------------
DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'

# ---------------------------------------------------------------------------
# Celery — no worker on Railway by default; run tasks synchronously
# Override by setting ASYNC_TASKS=True and adding a worker service
# ---------------------------------------------------------------------------
if not os.environ.get('ASYNC_TASKS'):
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

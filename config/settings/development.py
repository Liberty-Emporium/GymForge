"""
GymForge — Development Settings
"""
from .base import *

DEBUG = True

ALLOWED_HOSTS = ['*']

# Override session security for local dev
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Use local PostgreSQL in dev (still needs django-tenants engine)
DATABASES['default'].update({
    'NAME': config('DB_NAME', default='gymforge_dev'),
    'USER': config('DB_USER', default='postgres'),
    'PASSWORD': config('DB_PASSWORD', default=''),
    'HOST': config('DB_HOST', default='localhost'),
    'PORT': config('DB_PORT', default='5432'),
})

# Use local file storage in dev instead of Cloudflare R2
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# Use console email backend in dev
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Django Debug Toolbar (optional — install separately)
INSTALLED_APPS += ['django_extensions']

# Celery — run tasks eagerly in dev (optional: set False to use real Redis)
CELERY_TASK_ALWAYS_EAGER = config('CELERY_TASK_ALWAYS_EAGER', default=True, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = True

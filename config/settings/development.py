"""
GymForge — Development Settings
Uses SQLite so you can run locally with zero infrastructure.
"""
from .base import *

DEBUG = True
ALLOWED_HOSTS = ['*']

# SQLite — no Postgres needed locally
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# No HTTPS in dev
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Local file storage instead of R2
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# Print emails to console
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Run Celery tasks inline (no Redis/worker needed)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

INSTALLED_APPS += ['django_extensions']

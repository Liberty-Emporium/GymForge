"""
GymForge — Base Settings (Single-Tenant)
Each Railway deployment is one gym. No django-tenants.
"""
from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config('SECRET_KEY', default='dev-secret-key-change-in-production')

DEBUG = False

ALLOWED_HOSTS = []

# ---------------------------------------------------------------------------
# Database — standard Django (Postgres on Railway, SQLite in dev)
# ---------------------------------------------------------------------------
import dj_database_url, os

_db_url = os.environ.get('DATABASE_URL', '')
if _db_url:
    DATABASES = {
        'default': dj_database_url.parse(
            _db_url,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ---------------------------------------------------------------------------
# Installed Apps — flat list, no shared/tenant split
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.admin',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # GymForge apps
    'apps.gym',           # replaces apps.tenants — single gym config
    'apps.accounts',
    'apps.core',
    'apps.gym_owner',
    'apps.manager',
    'apps.trainer',
    'apps.front_desk',
    'apps.cleaner',
    'apps.nutritionist',
    'apps.members',
    'apps.ai_coach',
    'apps.ai_owner',
    'apps.scheduling',
    'apps.checkin',
    'apps.billing',
    'apps.notifications',
    'apps.inventory',
    'apps.analytics',
    'apps.leads',
    'apps.community',
    'apps.loyalty',
    'apps.landing',
    'apps.payroll',
    'apps.shop',
    'apps.kiosk',
    'apps.setup',
    'apps.platform_admin',
    'apps.api',

    # Third-party
    'rest_framework',
    'django_celery_beat',
]

# ---------------------------------------------------------------------------
# Middleware — TenantMainMiddleware removed
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.accounts.middleware.GymAccessMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
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
                'apps.core.context_processors.gym_branding',
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Custom User Model
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = '/auth/login/'
LOGIN_REDIRECT_URL = '/auth/redirect/'
LOGOUT_REDIRECT_URL = '/auth/login/'

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & Media Files
# ---------------------------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

CELERY_BEAT_SCHEDULE = {
    'check-member-retention-daily': {
        'task': 'apps.members.tasks.check_member_retention',
        'schedule': 86400,  # daily
    },
    'send-birthday-messages-daily': {
        'task': 'apps.members.tasks.send_birthday_messages',
        'schedule': 86400,
    },
    'process-trial-statuses-daily': {
        'task': 'apps.members.tasks.process_trial_statuses',
        'schedule': 86400,
    },
}

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = 'anymail.backends.sendgrid.EmailBackend'
ANYMAIL = {
    'SENDGRID_API_KEY': config('SENDGRID_API_KEY', default=''),
}
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@gymforge.com')
SERVER_EMAIL = config('SERVER_EMAIL', default='errors@gymforge.com')

# ---------------------------------------------------------------------------
# File Storage — Cloudflare R2 (override in dev to use local filesystem)
# ---------------------------------------------------------------------------
AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID', default='')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY', default='')
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='')
AWS_S3_ENDPOINT_URL = config('AWS_S3_ENDPOINT_URL', default='')
AWS_DEFAULT_ACL = None
AWS_S3_FILE_OVERWRITE = False

# ---------------------------------------------------------------------------
# Stripe
# ---------------------------------------------------------------------------
STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY', default='')
STRIPE_PUBLISHABLE_KEY = config('STRIPE_PUBLISHABLE_KEY', default='')
STRIPE_WEBHOOK_SECRET = config('STRIPE_WEBHOOK_SECRET', default='')

# ---------------------------------------------------------------------------
# Anthropic / Claude AI
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY', default='')

# ---------------------------------------------------------------------------
# Firebase Cloud Messaging
# ---------------------------------------------------------------------------
FCM_SERVER_KEY = config('FCM_SERVER_KEY', default='')

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
SESSION_COOKIE_AGE = 86400 * 14  # 14 days
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# ---------------------------------------------------------------------------
# Single-tenant gym identity
# GYM_NAME / GYM_SLUG are set as Railway env vars per-deployment.
# The setup wizard also writes these into apps.gym.GymConfig on first run.
# ---------------------------------------------------------------------------
GYM_NAME = config('GYM_NAME', default='My Gym')
GYM_SLUG = config('GYM_SLUG', default='mygym')

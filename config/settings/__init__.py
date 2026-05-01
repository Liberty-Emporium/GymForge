"""
Auto-select settings module based on DJANGO_SETTINGS_MODULE or RAILWAY_ENVIRONMENT.
"""
import os

env = os.environ.get('RAILWAY_ENVIRONMENT', os.environ.get('APP_ENV', 'development'))

if 'production' in env.lower() or 'prod' in env.lower():
    from .production import *
else:
    from .development import *

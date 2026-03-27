# This makes Celery's app available as the default app
# so that @shared_task decorators in any app will use it.
from .celery import app as celery_app

__all__ = ('celery_app',)

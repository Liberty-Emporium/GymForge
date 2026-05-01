from django.apps import AppConfig


class GymAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.gym'
    label = 'gym'
    verbose_name = 'Gym Configuration'

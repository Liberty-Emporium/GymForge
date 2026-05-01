from django.contrib import admin
from .models import GymConfig


@admin.register(GymConfig)
class GymConfigAdmin(admin.ModelAdmin):
    list_display = ['gym_name', 'slug', 'owner_email', 'subscription_status', 'trial_active', 'created_at']
    readonly_fields = ['created_at', 'updated_at', 'trial_start_date']

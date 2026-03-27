from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Custom admin for the GymForge User model.
    Extends Django's built-in UserAdmin to expose the role, phone,
    and profile_photo fields.
    """

    list_display = (
        'username', 'email', 'get_full_name', 'role', 'phone',
        'is_active', 'is_staff', 'date_joined',
    )
    list_filter = ('role', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'phone')
    ordering = ('-date_joined',)

    # Add GymForge-specific fields to the change form
    fieldsets = BaseUserAdmin.fieldsets + (
        (_('GymForge Profile'), {
            'fields': ('role', 'phone', 'profile_photo'),
        }),
    )

    # Add role + phone to the add-user form
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (_('GymForge Profile'), {
            'classes': ('wide',),
            'fields': ('role', 'phone', 'email', 'first_name', 'last_name'),
        }),
    )

from django.contrib import admin
from django.utils.html import format_html

from .models import GymProfile, Location, LocationHours, Service


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------

class LocationHoursInline(admin.TabularInline):
    model = LocationHours
    extra = 0
    fields = ('day', 'open_time', 'close_time', 'is_closed')
    ordering = ('day',)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'address', 'phone', 'timezone', 'is_active', 'created_at')
    list_filter = ('is_active', 'timezone')
    search_fields = ('name', 'address', 'phone', 'email')
    ordering = ('name',)
    inlines = [LocationHoursInline]

    fieldsets = (
        ('Identity', {
            'fields': ('name', 'address', 'phone', 'email'),
        }),
        ('Settings', {
            'fields': ('timezone', 'is_active'),
        }),
    )


@admin.register(LocationHours)
class LocationHoursAdmin(admin.ModelAdmin):
    list_display = ('location', 'day', 'open_time', 'close_time', 'is_closed')
    list_filter = ('location', 'is_closed')
    ordering = ('location', 'day')


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'is_custom', 'description_short')
    list_filter = ('is_active', 'is_custom')
    search_fields = ('name',)
    ordering = ('name',)

    def description_short(self, obj):
        return obj.description[:80] + '…' if len(obj.description) > 80 else obj.description
    description_short.short_description = 'Description'


# ---------------------------------------------------------------------------
# GymProfile
# ---------------------------------------------------------------------------

@admin.register(GymProfile)
class GymProfileAdmin(admin.ModelAdmin):
    """
    Singleton admin — there is exactly one GymProfile per tenant schema.
    Prevent adding a second one and disable deletion.
    """

    list_display = (
        'gym_name', 'primary_color_swatch', 'accent_color_swatch',
        'landing_page_active', 'custom_domain_active', 'updated_at',
    )

    fieldsets = (
        ('Identity', {
            'fields': ('gym_name', 'logo', 'tagline', 'about_text', 'welcome_message'),
        }),
        ('Branding', {
            'fields': ('primary_color', 'accent_color', 'homepage_layout', 'banner_image'),
            'description': (
                'Colors must be 6-digit hex values (e.g. #1a1a2e). '
                'GymForge branding must NEVER appear in member or owner views.'
            ),
        }),
        ('Social Links', {
            'fields': (
                'social_instagram', 'social_facebook',
                'social_tiktok', 'social_youtube',
            ),
            'classes': ('collapse',),
        }),
        ('Custom Domain', {
            'fields': ('custom_domain', 'custom_domain_active'),
            'classes': ('collapse',),
        }),
        ('Legal & Comms', {
            'fields': ('waiver_text', 'email_signature'),
            'classes': ('collapse',),
        }),
        ('Features', {
            'fields': ('features_enabled',),
            'classes': ('collapse',),
        }),
        ('Landing Page', {
            'fields': ('landing_page_active', 'landing_page_sections'),
            'classes': ('collapse',),
        }),
    )

    readonly_fields = ('updated_at',)

    def primary_color_swatch(self, obj):
        return format_html(
            '<span style="display:inline-block;width:24px;height:24px;'
            'background:{};border-radius:4px;border:1px solid #ccc" '
            'title="{}"></span>',
            obj.primary_color, obj.primary_color,
        )
    primary_color_swatch.short_description = 'Primary'

    def accent_color_swatch(self, obj):
        return format_html(
            '<span style="display:inline-block;width:24px;height:24px;'
            'background:{};border-radius:4px;border:1px solid #ccc" '
            'title="{}"></span>',
            obj.accent_color, obj.accent_color,
        )
    accent_color_swatch.short_description = 'Accent'

    def has_add_permission(self, request):
        """Only one GymProfile per tenant — block adding a second."""
        from .models import GymProfile
        if GymProfile.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        """GymProfile must never be deleted — edit it instead."""
        return False

from django.contrib import admin
from django.utils.html import format_html

from .models import AuditLog, Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    """GymForge SaaS plans — Starter / Growth / Pro."""

    list_display = ('name', 'price_monthly', 'max_members', 'max_locations', 'stripe_price_id', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'stripe_price_id')
    ordering = ('price_monthly',)
    fieldsets = (
        ('Plan Details', {'fields': ('name', 'price_monthly', 'max_members', 'max_locations', 'is_active')}),
        ('Stripe', {'fields': ('stripe_price_id',)}),
        ('Features', {'fields': ('features',), 'classes': ('collapse',)}),
    )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    IMMUTABLE — no add, change, or delete is ever permitted.

    The AuditLog is a forensic record. Any modification would destroy its
    evidentiary value. All write operations go through AuditLog.log().
    """

    list_display = (
        'timestamp', 'actor_email', 'schema_badge', 'action',
        'target_model', 'target_id', 'ip_address',
    )
    list_filter = ('gym_schema', 'target_model')
    search_fields = ('actor_email', 'action', 'gym_schema', 'target_model')
    ordering = ('-timestamp',)
    date_hierarchy = 'timestamp'

    # Every field is read-only — the row is set once at creation
    readonly_fields = (
        'actor_email', 'gym_schema', 'action', 'target_model',
        'target_id', 'details', 'timestamp', 'ip_address',
    )

    fieldsets = (
        ('Event', {
            'fields': ('timestamp', 'actor_email', 'gym_schema', 'ip_address'),
        }),
        ('Action', {
            'fields': ('action', 'target_model', 'target_id'),
        }),
        ('Details', {
            'fields': ('details',),
            'classes': ('collapse',),
        }),
    )

    def schema_badge(self, obj):
        if obj.gym_schema:
            return format_html(
                '<span style="background:#3b82f6;color:#fff;padding:2px 8px;'
                'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
                obj.gym_schema,
            )
        return format_html(
            '<span style="background:#6b7280;color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">public</span>'
        )
    schema_badge.short_description = 'Schema'

    # ------------------------------------------------------------------
    # Hard immutability — all three permission methods return False
    # ------------------------------------------------------------------

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

from django.contrib import admin
from django.utils.html import format_html

from .models import GymTenant, GymDomain


class GymDomainInline(admin.TabularInline):
    """Show all domains for a tenant inline on the GymTenant change page."""
    model = GymDomain
    extra = 1
    fields = ('domain', 'is_primary')
    readonly_fields = ()


@admin.register(GymTenant)
class GymTenantAdmin(admin.ModelAdmin):
    """
    Platform Owner view of all gym tenants.
    Lives in the public schema — only accessible via /django-admin/ on the
    platform domain (not a gym subdomain).

    CardScanLog and AuditLog are IMMUTABLE — no edit/delete ever allowed here.
    """

    list_display = (
        'gym_name',
        'schema_name',
        'owner_email',
        'subscription_status_badge',
        'trial_active',
        'trial_days_remaining',
        'member_app_active',
        'plan',
        'created_at',
    )
    list_filter = ('subscription_status', 'trial_active', 'member_app_active', 'plan')
    search_fields = ('gym_name', 'schema_name', 'owner_email')
    ordering = ('-created_at',)
    readonly_fields = (
        'schema_name',
        'trial_start_date',
        'created_at',
        'trial_days_remaining',
    )

    fieldsets = (
        ('Identity', {
            'fields': ('gym_name', 'schema_name', 'owner_email', 'plan'),
        }),
        ('Subscription', {
            'fields': (
                'subscription_status',
                'trial_active',
                'trial_start_date',
                'trial_days_remaining',
                'member_app_active',
            ),
        }),
        ('Stripe', {
            'fields': ('stripe_customer_id', 'stripe_subscription_id'),
            'classes': ('collapse',),
        }),
        ('Lifecycle', {
            'fields': ('data_retention_until', 'created_at'),
            'classes': ('collapse',),
        }),
    )

    inlines = [GymDomainInline]

    def subscription_status_badge(self, obj):
        colours = {
            'trial': '#f59e0b',
            'active': '#10b981',
            'suspended': '#ef4444',
            'cancelled': '#6b7280',
        }
        colour = colours.get(obj.subscription_status, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;'
            'font-size:11px;font-weight:600">{}</span>',
            colour,
            obj.get_subscription_status_display(),
        )
    subscription_status_badge.short_description = 'Status'

    def trial_days_remaining(self, obj):
        days = obj.trial_days_remaining
        if not obj.trial_active:
            return '—'
        colour = '#ef4444' if days <= 3 else '#f59e0b' if days <= 7 else '#10b981'
        return format_html(
            '<span style="color:{};font-weight:600">{} days</span>',
            colour,
            max(days, 0),
        )
    trial_days_remaining.short_description = 'Trial remaining'

    # ------------------------------------------------------------------
    # Safety: prevent accidental schema deletion from the admin
    # ------------------------------------------------------------------
    def has_delete_permission(self, request, obj=None):
        """
        Deleting a GymTenant from admin would drop the PostgreSQL schema.
        Force this through the cancellation workflow instead (Step 44).
        """
        return False


@admin.register(GymDomain)
class GymDomainAdmin(admin.ModelAdmin):
    list_display = ('domain', 'tenant', 'is_primary')
    list_filter = ('is_primary',)
    search_fields = ('domain', 'tenant__gym_name')
    ordering = ('tenant__gym_name', '-is_primary')
    readonly_fields = ()

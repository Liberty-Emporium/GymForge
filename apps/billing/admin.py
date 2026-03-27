from django.contrib import admin
from django.utils.html import format_html

from .models import (
    CardPurchase,
    MemberMembership,
    MembershipTier,
    MemberTab,
    NoShowCharge,
)

# Plan is registered in apps/platform_admin/admin.py (it lives in the public schema).


# ---------------------------------------------------------------------------
# MembershipTier — tenant schema; managed by Gym Owner
# ---------------------------------------------------------------------------

@admin.register(MembershipTier)
class MembershipTierAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'price', 'billing_cycle', 'trial_days',
        'no_show_fee', 'late_cancel_fee', 'cancellation_window_hours', 'is_active',
    )
    list_filter = ('billing_cycle', 'is_active')
    search_fields = ('name',)
    ordering = ('price',)
    filter_horizontal = ('included_services',)

    fieldsets = (
        ('Tier Details', {
            'fields': ('name', 'price', 'billing_cycle', 'description', 'is_active', 'trial_days'),
        }),
        ('Services Included', {
            'fields': ('included_services',),
        }),
        ('Cancellation Policy', {
            'fields': ('cancellation_window_hours', 'no_show_fee', 'late_cancel_fee'),
        }),
    )


# ---------------------------------------------------------------------------
# MemberMembership — tenant schema
# ---------------------------------------------------------------------------

@admin.register(MemberMembership)
class MemberMembershipAdmin(admin.ModelAdmin):
    list_display = (
        'member', 'tier', 'status_badge', 'start_date', 'end_date',
        'overdue_since', 'stripe_subscription_id',
    )
    list_filter = ('status', 'tier')
    search_fields = (
        'member__user__first_name', 'member__user__last_name',
        'member__user__email', 'stripe_subscription_id',
    )
    ordering = ('-start_date',)
    readonly_fields = ('overdue_since',)

    def status_badge(self, obj):
        colours = {
            'active': '#10b981',
            'expiring': '#f59e0b',
            'overdue': '#ef4444',
            'suspended': '#dc2626',
            'cancelled': '#6b7280',
            'frozen': '#3b82f6',
        }
        colour = colours.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            colour, obj.get_status_display(),
        )
    status_badge.short_description = 'Status'


# ---------------------------------------------------------------------------
# MemberTab — tenant schema
# ---------------------------------------------------------------------------

@admin.register(MemberTab)
class MemberTabAdmin(admin.ModelAdmin):
    list_display = ('member', 'balance', 'spending_limit', 'over_limit_flag', 'last_charged')
    search_fields = ('member__user__first_name', 'member__user__last_name', 'member__user__email')
    ordering = ('-balance',)
    readonly_fields = ('last_charged',)

    def over_limit_flag(self, obj):
        if obj.is_over_limit:
            return format_html('<span style="color:#ef4444;font-weight:600">⚠ Over limit</span>')
        return '—'
    over_limit_flag.short_description = 'Limit'


# ---------------------------------------------------------------------------
# CardPurchase — tenant schema; IMMUTABLE — no edit/delete
# ---------------------------------------------------------------------------

@admin.register(CardPurchase)
class CardPurchaseAdmin(admin.ModelAdmin):
    list_display = (
        'processed_at', 'member_name', 'item_description', 'amount',
        'status', 'device', 'stripe_payment_intent',
    )
    list_filter = ('status', 'device')
    search_fields = (
        'card__member__user__first_name', 'card__member__user__last_name',
        'item_description', 'stripe_payment_intent',
    )
    ordering = ('-processed_at',)
    readonly_fields = (
        'card', 'device', 'item_description', 'amount',
        'processed_at', 'stripe_payment_intent', 'status',
    )

    def member_name(self, obj):
        return obj.card.member.user.get_full_name()
    member_name.short_description = 'Member'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# NoShowCharge — tenant schema; IMMUTABLE — no edit/delete
# ---------------------------------------------------------------------------

@admin.register(NoShowCharge)
class NoShowChargeAdmin(admin.ModelAdmin):
    list_display = (
        'charged_at', 'member', 'charge_type', 'amount',
        'status', 'stripe_payment_intent',
    )
    list_filter = ('charge_type', 'status')
    search_fields = (
        'member__user__first_name', 'member__user__last_name',
        'stripe_payment_intent',
    )
    ordering = ('-charged_at',)
    readonly_fields = (
        'member', 'booking', 'amount', 'charge_type',
        'stripe_payment_intent', 'charged_at', 'status',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

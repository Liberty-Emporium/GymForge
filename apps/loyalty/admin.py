from django.contrib import admin
from django.utils.html import format_html

from .models import (
    LoyaltyRule,
    LoyaltyTransaction,
    LoyaltyReward,
    BadgeMilestone,
    MemberBadge,
)


# ---------------------------------------------------------------------------
# LoyaltyRule
# ---------------------------------------------------------------------------

@admin.register(LoyaltyRule)
class LoyaltyRuleAdmin(admin.ModelAdmin):
    list_display = ('action', 'points', 'max_per_day', 'is_active', 'description')
    list_filter = ('is_active',)
    ordering = ('action',)

    fieldsets = (
        ('Rule', {
            'fields': ('action', 'points', 'description', 'is_active'),
        }),
        ('Cap', {
            'fields': ('max_per_day',),
            'description': 'Optional: limit how many times this rule fires per member per day.',
        }),
    )


# ---------------------------------------------------------------------------
# LoyaltyTransaction  (immutable ledger — no add/change/delete)
# ---------------------------------------------------------------------------

@admin.register(LoyaltyTransaction)
class LoyaltyTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'created_at', 'member', 'points_display', 'transaction_type', 'action', 'description',
    )
    list_filter = ('transaction_type', 'action')
    search_fields = ('member__user__first_name', 'member__user__last_name', 'description')
    ordering = ('-created_at',)
    readonly_fields = (
        'member', 'points', 'transaction_type', 'action',
        'description', 'created_at', 'created_by',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def points_display(self, obj):
        colour = '#10b981' if obj.points >= 0 else '#ef4444'
        sign = '+' if obj.points >= 0 else ''
        return format_html(
            '<span style="color:{};font-weight:600">{}{}</span>',
            colour, sign, obj.points,
        )
    points_display.short_description = 'Points'


# ---------------------------------------------------------------------------
# LoyaltyReward
# ---------------------------------------------------------------------------

@admin.register(LoyaltyReward)
class LoyaltyRewardAdmin(admin.ModelAdmin):
    list_display = ('name', 'reward_type', 'points_cost', 'stock', 'is_active', 'is_available')
    list_filter = ('reward_type', 'is_active')
    search_fields = ('name', 'description')
    ordering = ('points_cost',)
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Reward', {
            'fields': ('name', 'description', 'reward_type', 'image'),
        }),
        ('Availability', {
            'fields': ('points_cost', 'stock', 'is_active'),
        }),
        ('Meta', {
            'fields': ('created_at',),
        }),
    )

    def is_available(self, obj):
        if obj.is_available:
            return format_html('<span style="color:#10b981;font-weight:600">Yes</span>')
        return format_html('<span style="color:#ef4444;font-weight:600">No</span>')
    is_available.short_description = 'Available?'


# ---------------------------------------------------------------------------
# BadgeMilestone
# ---------------------------------------------------------------------------

@admin.register(BadgeMilestone)
class BadgeMilestoneAdmin(admin.ModelAdmin):
    list_display = ('name', 'badge_type', 'threshold', 'points_reward', 'is_active')
    list_filter = ('badge_type', 'is_active')
    search_fields = ('name', 'description')
    ordering = ('badge_type', 'threshold')

    fieldsets = (
        ('Badge', {
            'fields': ('name', 'description', 'badge_type', 'threshold', 'icon'),
        }),
        ('Reward', {
            'fields': ('points_reward', 'is_active'),
        }),
    )


# ---------------------------------------------------------------------------
# MemberBadge
# ---------------------------------------------------------------------------

@admin.register(MemberBadge)
class MemberBadgeAdmin(admin.ModelAdmin):
    list_display = ('member', 'milestone', 'earned_at')
    list_filter = ('milestone',)
    search_fields = ('member__user__first_name', 'member__user__last_name')
    ordering = ('-earned_at',)
    readonly_fields = ('earned_at',)

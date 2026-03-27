from django.contrib import admin
from django.utils.html import format_html

from .models import (
    BodyMetric,
    FamilyAccount,
    HealthProfile,
    MemberProfile,
    NutritionRecommendation,
    SupplementRecommendation,
    WorkoutLog,
)


# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------

class HealthProfileInline(admin.StackedInline):
    model = HealthProfile
    extra = 0
    can_delete = False
    fields = (
        'fitness_goal', 'activity_level', 'dietary_preference',
        'injuries_limitations', 'medical_conditions', 'intake_completed',
    )
    readonly_fields = ('last_updated',)


class WorkoutLogInline(admin.TabularInline):
    model = WorkoutLog
    extra = 0
    fields = ('workout_date', 'source', 'duration_minutes', 'exercise_count_display', 'mood_before', 'energy_after')
    readonly_fields = ('workout_date', 'source', 'duration_minutes', 'exercise_count_display', 'mood_before', 'energy_after')

    def exercise_count_display(self, obj):
        return obj.exercise_count
    exercise_count_display.short_description = 'Exercises'

    def has_add_permission(self, request, obj=None):
        return False


class BodyMetricInline(admin.TabularInline):
    model = BodyMetric
    extra = 0
    fields = ('recorded_at', 'weight_kg', 'body_fat_percent')
    readonly_fields = ('recorded_at',)


# ---------------------------------------------------------------------------
# FamilyAccount
# ---------------------------------------------------------------------------

@admin.register(FamilyAccount)
class FamilyAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'primary_member', 'member_count', 'created_at')
    search_fields = ('name', 'primary_member__user__first_name', 'primary_member__user__last_name')
    ordering = ('name',)
    readonly_fields = ('created_at',)

    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = 'Members'


# ---------------------------------------------------------------------------
# MemberProfile
# ---------------------------------------------------------------------------

@admin.register(MemberProfile)
class MemberProfileAdmin(admin.ModelAdmin):
    """
    Business rule: a member can ONLY see their own data.
    Enforce queryset-level filtering in all non-admin views.
    This admin is accessible only to platform_admin and gym_owner roles.
    """

    list_display = (
        'full_name', 'email', 'primary_location', 'join_date',
        'waiver_badge', 'intake_badge', 'loyalty_points', 'referral_code',
    )
    list_filter = ('waiver_signed', 'primary_location', 'family_account')
    search_fields = (
        'user__first_name', 'user__last_name',
        'user__email', 'referral_code',
    )
    ordering = ('-join_date',)
    readonly_fields = ('join_date', 'referral_code', 'waiver_signed_at')

    fieldsets = (
        ('User', {
            'fields': ('user',),
        }),
        ('Personal', {
            'fields': ('date_of_birth', 'primary_location'),
        }),
        ('Emergency Contact', {
            'fields': ('emergency_contact_name', 'emergency_contact_phone'),
            'classes': ('collapse',),
        }),
        ('Waiver', {
            'fields': ('waiver_signed', 'waiver_signed_at'),
        }),
        ('Loyalty & Referrals', {
            'fields': ('loyalty_points', 'referral_code', 'referred_by'),
            'classes': ('collapse',),
        }),
        ('Family Billing', {
            'fields': ('family_account',),
            'classes': ('collapse',),
        }),
    )

    inlines = [HealthProfileInline, WorkoutLogInline, BodyMetricInline]

    def waiver_badge(self, obj):
        if obj.waiver_signed:
            return format_html('<span style="color:#10b981;font-weight:600">✓ Signed</span>')
        return format_html('<span style="color:#ef4444;font-weight:600">✗ Unsigned</span>')
    waiver_badge.short_description = 'Waiver'

    def intake_badge(self, obj):
        if obj.has_completed_intake:
            return format_html('<span style="color:#10b981;font-weight:600">✓ Complete</span>')
        return format_html('<span style="color:#f59e0b;font-weight:600">Pending</span>')
    intake_badge.short_description = 'Intake'


# ---------------------------------------------------------------------------
# HealthProfile
# ---------------------------------------------------------------------------

@admin.register(HealthProfile)
class HealthProfileAdmin(admin.ModelAdmin):
    list_display = (
        'member', 'fitness_goal', 'activity_level',
        'dietary_preference', 'intake_completed', 'last_updated',
    )
    list_filter = ('intake_completed', 'activity_level', 'dietary_preference', 'prefers_group')
    search_fields = ('member__user__first_name', 'member__user__last_name', 'fitness_goal')
    ordering = ('-last_updated',)
    readonly_fields = ('last_updated',)

    fieldsets = (
        ('Member', {'fields': ('member',)}),
        ('Goals', {
            'fields': ('fitness_goal', 'goal_detail', 'goal_timeline_weeks', 'activity_level'),
        }),
        ('Health History', {
            'fields': ('injuries_limitations', 'medical_conditions', 'medications'),
            'classes': ('collapse',),
        }),
        ('Lifestyle', {
            'fields': ('sleep_hours', 'stress_level'),
            'classes': ('collapse',),
        }),
        ('Nutrition', {
            'fields': (
                'dietary_preference', 'food_allergies', 'disliked_foods',
                'current_supplements', 'typical_diet_description', 'water_intake_liters',
            ),
            'classes': ('collapse',),
        }),
        ('Training Preferences', {
            'fields': ('preferred_workout_time', 'prefers_group', 'has_worked_with_trainer', 'past_obstacles'),
            'classes': ('collapse',),
        }),
        ('Intake Status', {
            'fields': ('intake_completed', 'raw_intake_data', 'last_updated'),
        }),
    )


# ---------------------------------------------------------------------------
# WorkoutLog
# ---------------------------------------------------------------------------

@admin.register(WorkoutLog)
class WorkoutLogAdmin(admin.ModelAdmin):
    list_display = (
        'member', 'workout_date', 'source', 'duration_minutes',
        'exercise_count', 'mood_before', 'energy_after', 'logged_at',
    )
    list_filter = ('source', 'workout_date')
    search_fields = ('member__user__first_name', 'member__user__last_name')
    ordering = ('-workout_date',)
    readonly_fields = ('logged_at',)

    def exercise_count(self, obj):
        return obj.exercise_count
    exercise_count.short_description = 'Exercises'


# ---------------------------------------------------------------------------
# BodyMetric
# ---------------------------------------------------------------------------

@admin.register(BodyMetric)
class BodyMetricAdmin(admin.ModelAdmin):
    list_display = ('member', 'recorded_at', 'weight_kg', 'body_fat_percent')
    list_filter = ('recorded_at',)
    search_fields = ('member__user__first_name', 'member__user__last_name')
    ordering = ('-recorded_at',)


# ---------------------------------------------------------------------------
# NutritionRecommendation
# ---------------------------------------------------------------------------

@admin.register(NutritionRecommendation)
class NutritionRecommendationAdmin(admin.ModelAdmin):
    list_display = (
        'member', 'generated_at', 'daily_calories',
        'protein_g', 'carbs_g', 'fat_g', 'nutritionist_reviewed',
    )
    list_filter = ('nutritionist_reviewed',)
    search_fields = ('member__user__first_name', 'member__user__last_name')
    ordering = ('-generated_at',)
    readonly_fields = ('generated_at',)

    fieldsets = (
        ('Member', {'fields': ('member', 'generated_at')}),
        ('Macro Targets', {
            'fields': ('daily_calories', 'protein_g', 'carbs_g', 'fat_g'),
        }),
        ('Meal Plan', {
            'fields': ('meal_plan',),
        }),
        ('Nutritionist Review', {
            'fields': ('nutritionist_reviewed', 'nutritionist_notes'),
        }),
    )


# ---------------------------------------------------------------------------
# SupplementRecommendation
# ---------------------------------------------------------------------------

@admin.register(SupplementRecommendation)
class SupplementRecommendationAdmin(admin.ModelAdmin):
    """
    IMPORTANT: All views displaying these records must append
    SupplementRecommendation.SUPPLEMENT_DISCLAIMER. This admin
    shows the disclaimer as a persistent notice.
    """

    list_display = (
        'member', 'supplement_name', 'suggested_dosage',
        'best_time_to_take', 'member_already_takes',
        'has_override', 'generated_at',
    )
    list_filter = ('member_already_takes',)
    search_fields = (
        'member__user__first_name', 'member__user__last_name',
        'supplement_name',
    )
    ordering = ('-generated_at',)
    readonly_fields = ('generated_at', 'disclaimer_notice')

    fieldsets = (
        ('⚠ Medical Disclaimer', {
            'fields': ('disclaimer_notice',),
            'description': (
                'This disclaimer MUST appear on every page that shows supplement '
                'recommendations. It is stored in SupplementRecommendation.SUPPLEMENT_DISCLAIMER.'
            ),
        }),
        ('Member', {'fields': ('member', 'generated_at')}),
        ('Recommendation', {
            'fields': (
                'supplement_name', 'reason',
                'suggested_dosage', 'best_time_to_take',
                'member_already_takes',
            ),
        }),
        ('Professional Override', {
            'fields': ('professional_override', 'override_by'),
            'classes': ('collapse',),
        }),
    )

    def disclaimer_notice(self, obj):
        return format_html(
            '<div style="background:#fef3c7;border:1px solid #f59e0b;padding:10px;'
            'border-radius:6px;font-size:13px">'
            '<strong>Disclaimer (must appear in all templates):</strong><br>{}'
            '</div>',
            SupplementRecommendation.SUPPLEMENT_DISCLAIMER,
        )
    disclaimer_notice.short_description = 'Disclaimer'

    def has_override(self, obj):
        if obj.professional_override:
            return format_html('<span style="color:#3b82f6;font-weight:600">✓ Overridden</span>')
        return '—'
    has_override.short_description = 'Override'

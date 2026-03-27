from django.contrib import admin
from django.utils.html import format_html

from .models import (
    AccessRule,
    CheckIn,
    CleaningTask,
    ClientAssignment,
    DoorDevice,
    LockerAssignment,
    MemberCard,
    MemberNote,
    Shift,
    StaffRequest,
    TaskTemplate,
    TrainerProfile,
    CardScanLog,
)


# ---------------------------------------------------------------------------
# MemberCard
# ---------------------------------------------------------------------------

@admin.register(MemberCard)
class MemberCardAdmin(admin.ModelAdmin):
    list_display = (
        'card_number', 'member', 'is_active', 'issued_at',
        'issued_by', 'deactivated_at', 'deactivation_reason',
    )
    list_filter = ('is_active',)
    search_fields = ('card_number', 'member__user__first_name', 'member__user__last_name')
    ordering = ('-issued_at',)
    readonly_fields = ('issued_at', 'rfid_token', 'deactivated_at')

    fieldsets = (
        ('Card', {
            'fields': ('card_number', 'rfid_token', 'member', 'issued_by', 'issued_at'),
        }),
        ('Status', {
            'fields': ('is_active', 'deactivated_at', 'deactivation_reason'),
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        # Once a card is created, rfid_token must never be editable
        if obj:
            return self.readonly_fields + ('member',)
        return self.readonly_fields


# ---------------------------------------------------------------------------
# DoorDevice
# ---------------------------------------------------------------------------

@admin.register(DoorDevice)
class DoorDeviceAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'location', 'device_type', 'is_active',
        'last_seen', 'ip_address',
    )
    list_filter = ('device_type', 'is_active', 'location')
    search_fields = ('name', 'location__name')
    ordering = ('location', 'name')
    readonly_fields = ('last_seen', 'ip_address')

    fieldsets = (
        ('Device', {
            'fields': ('name', 'location', 'device_type', 'is_active'),
        }),
        ('Auth', {
            'fields': ('device_token',),
            'description': 'This token is used by the Raspberry Pi door agent to authenticate API calls.',
        }),
        ('Status', {
            'fields': ('last_seen', 'ip_address'),
        }),
    )


# ---------------------------------------------------------------------------
# CardScanLog — IMMUTABLE
# ---------------------------------------------------------------------------

@admin.register(CardScanLog)
class CardScanLogAdmin(admin.ModelAdmin):
    """
    IMMUTABLE — CardScanLog is the authoritative access audit trail.
    No add, change, or delete is ever permitted (Section 17).
    """

    list_display = (
        'scanned_at', 'card_number', 'member_name',
        'device', 'scan_type', 'result_badge',
    )
    list_filter = ('result', 'scan_type', 'device__location')
    search_fields = (
        'card__card_number',
        'card__member__user__first_name',
        'card__member__user__last_name',
        'device__name',
    )
    ordering = ('-scanned_at',)
    date_hierarchy = 'scanned_at'
    readonly_fields = ('card', 'device', 'scanned_at', 'result', 'scan_type')

    def card_number(self, obj):
        return obj.card.card_number
    card_number.short_description = 'Card'

    def member_name(self, obj):
        return obj.card.member.full_name
    member_name.short_description = 'Member'

    def result_badge(self, obj):
        colours = {
            'granted': '#10b981',
            'denied_inactive': '#ef4444',
            'denied_payment': '#f59e0b',
            'denied_suspended': '#dc2626',
            'denied_hours': '#6b7280',
            'denied_unknown': '#9ca3af',
        }
        colour = colours.get(obj.result, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            colour, obj.get_result_display(),
        )
    result_badge.short_description = 'Result'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# LockerAssignment
# ---------------------------------------------------------------------------

@admin.register(LockerAssignment)
class LockerAssignmentAdmin(admin.ModelAdmin):
    list_display = ('locker_number', 'location', 'member', 'is_active', 'assigned_at')
    list_filter = ('is_active', 'location')
    search_fields = ('locker_number', 'member__user__first_name', 'member__user__last_name')
    ordering = ('location', 'locker_number')
    readonly_fields = ('assigned_at',)


# ---------------------------------------------------------------------------
# CheckIn
# ---------------------------------------------------------------------------

@admin.register(CheckIn)
class CheckInAdmin(admin.ModelAdmin):
    list_display = (
        'checked_in_at', 'member', 'location', 'method',
        'is_guest', 'duration_display', 'checked_out_at',
    )
    list_filter = ('method', 'is_guest', 'location')
    search_fields = ('member__user__first_name', 'member__user__last_name')
    ordering = ('-checked_in_at',)
    readonly_fields = ('checked_in_at',)

    def duration_display(self, obj):
        mins = obj.duration_minutes
        if mins is None:
            return format_html('<span style="color:#f59e0b">Still in gym</span>')
        return f'{mins} min'
    duration_display.short_description = 'Duration'


# ---------------------------------------------------------------------------
# AccessRule
# ---------------------------------------------------------------------------

@admin.register(AccessRule)
class AccessRuleAdmin(admin.ModelAdmin):
    list_display = (
        'membership_tier', 'location', 'access_start_time',
        'access_end_time', 'days_allowed', 'is_active',
    )
    list_filter = ('is_active', 'location', 'membership_tier')
    ordering = ('location', 'membership_tier')


# ---------------------------------------------------------------------------
# Shift
# ---------------------------------------------------------------------------

@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = (
        'date', 'staff', 'location', 'start_time',
        'end_time', 'attended_badge',
    )
    list_filter = ('location', 'attended', 'date')
    search_fields = ('staff__first_name', 'staff__last_name')
    ordering = ('-date', 'start_time')

    def attended_badge(self, obj):
        if obj.attended is None:
            return '—'
        if obj.attended:
            return format_html('<span style="color:#10b981;font-weight:600">✓ Yes</span>')
        return format_html('<span style="color:#ef4444;font-weight:600">✗ No</span>')
    attended_badge.short_description = 'Attended'


# ---------------------------------------------------------------------------
# StaffRequest
# ---------------------------------------------------------------------------

@admin.register(StaffRequest)
class StaffRequestAdmin(admin.ModelAdmin):
    list_display = (
        'created_at', 'request_type', 'target_email',
        'role', 'location', 'requested_by', 'status',
    )
    list_filter = ('request_type', 'status', 'location')
    search_fields = ('target_email', 'requested_by__first_name', 'requested_by__last_name')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)


# ---------------------------------------------------------------------------
# MemberNote
# ---------------------------------------------------------------------------

@admin.register(MemberNote)
class MemberNoteAdmin(admin.ModelAdmin):
    list_display = ('member', 'author', 'visibility', 'content_short', 'created_at')
    list_filter = ('visibility',)
    search_fields = (
        'member__user__first_name', 'member__user__last_name',
        'author__first_name', 'author__last_name',
    )
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)

    def content_short(self, obj):
        return obj.content[:80] + '…' if len(obj.content) > 80 else obj.content
    content_short.short_description = 'Note'


# ---------------------------------------------------------------------------
# ClientAssignment
# ---------------------------------------------------------------------------

@admin.register(ClientAssignment)
class ClientAssignmentAdmin(admin.ModelAdmin):
    list_display = ('staff', 'member', 'assignment_type', 'is_active', 'start_date')
    list_filter = ('assignment_type', 'is_active')
    search_fields = (
        'staff__first_name', 'staff__last_name',
        'member__user__first_name', 'member__user__last_name',
    )
    ordering = ('-start_date',)
    readonly_fields = ('start_date',)


# ---------------------------------------------------------------------------
# TaskTemplate
# ---------------------------------------------------------------------------

@admin.register(TaskTemplate)
class TaskTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'area', 'shift_type', 'priority')
    list_filter = ('shift_type', 'location')
    search_fields = ('name', 'area')
    ordering = ('location', 'shift_type', 'priority')


# ---------------------------------------------------------------------------
# CleaningTask
# ---------------------------------------------------------------------------

@admin.register(CleaningTask)
class CleaningTaskAdmin(admin.ModelAdmin):
    list_display = (
        'shift_date', 'template', 'assigned_to',
        'completed_badge', 'completed_at',
    )
    list_filter = ('completed', 'shift_date', 'template__location')
    search_fields = ('assigned_to__first_name', 'assigned_to__last_name', 'template__name')
    ordering = ('-shift_date', 'template__priority')
    readonly_fields = ('completed_at',)

    def completed_badge(self, obj):
        if obj.completed:
            return format_html('<span style="color:#10b981;font-weight:600">✓ Done</span>')
        return format_html('<span style="color:#f59e0b;font-weight:600">Pending</span>')
    completed_badge.short_description = 'Status'


# ---------------------------------------------------------------------------
# TrainerProfile
# ---------------------------------------------------------------------------

@admin.register(TrainerProfile)
class TrainerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'specialties', 'certifications', 'is_visible_to_members')
    list_filter = ('is_visible_to_members',)
    search_fields = ('user__first_name', 'user__last_name', 'specialties')
    ordering = ('user__last_name',)

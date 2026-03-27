from django.contrib import admin
from django.utils.html import format_html

from .models import Appointment, Booking, ClassSession, ClassType, WorkoutPlan


# ---------------------------------------------------------------------------
# ClassType
# ---------------------------------------------------------------------------

@admin.register(ClassType)
class ClassTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'duration_minutes', 'is_active', 'session_count')
    list_filter = ('is_active',)
    search_fields = ('name',)
    ordering = ('name',)

    def session_count(self, obj):
        return obj.sessions.count()
    session_count.short_description = 'Sessions'


# ---------------------------------------------------------------------------
# ClassSession
# ---------------------------------------------------------------------------

class BookingInline(admin.TabularInline):
    model = Booking
    extra = 0
    fields = ('member', 'status', 'booked_at', 'waitlist_position', 'no_show_fee_charged')
    readonly_fields = ('booked_at',)
    ordering = ('status', 'booked_at')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ClassSession)
class ClassSessionAdmin(admin.ModelAdmin):
    list_display = (
        'start_datetime', 'class_type', 'location', 'trainer',
        'capacity', 'confirmed_count', 'waitlist_count',
        'spots_remaining', 'cancelled_badge',
    )
    list_filter = ('is_cancelled', 'class_type', 'location')
    search_fields = ('class_type__name', 'trainer__first_name', 'trainer__last_name')
    ordering = ('-start_datetime',)
    date_hierarchy = 'start_datetime'
    readonly_fields = ('confirmed_count', 'waitlist_count', 'spots_remaining')

    fieldsets = (
        ('Session', {
            'fields': ('class_type', 'location', 'trainer', 'start_datetime', 'end_datetime', 'capacity'),
        }),
        ('Status', {
            'fields': ('is_cancelled', 'cancellation_reason'),
        }),
        ('Notes', {
            'fields': ('session_notes',),
            'classes': ('collapse',),
        }),
        ('Booking Summary', {
            'fields': ('confirmed_count', 'waitlist_count', 'spots_remaining'),
        }),
    )

    inlines = [BookingInline]

    def confirmed_count(self, obj):
        return obj.confirmed_count
    confirmed_count.short_description = 'Confirmed'

    def waitlist_count(self, obj):
        return obj.waitlist_count
    waitlist_count.short_description = 'Waitlist'

    def spots_remaining(self, obj):
        remaining = obj.spots_remaining
        colour = '#ef4444' if remaining == 0 else '#10b981'
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            colour, remaining,
        )
    spots_remaining.short_description = 'Spots left'

    def cancelled_badge(self, obj):
        if obj.is_cancelled:
            return format_html(
                '<span style="background:#ef4444;color:#fff;padding:2px 8px;'
                'border-radius:4px;font-size:11px;font-weight:600">Cancelled</span>'
            )
        return ''
    cancelled_badge.short_description = 'Cancelled'


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        'booked_at', 'member', 'class_session', 'status_badge',
        'waitlist_position', 'no_show_fee_charged',
    )
    list_filter = ('status', 'no_show_fee_charged')
    search_fields = (
        'member__user__first_name', 'member__user__last_name',
        'class_session__class_type__name',
    )
    ordering = ('-booked_at',)
    readonly_fields = ('booked_at', 'cancelled_at')

    fieldsets = (
        ('Booking', {
            'fields': ('member', 'class_session', 'status', 'booked_at', 'cancelled_at'),
        }),
        ('Waitlist', {
            'fields': ('waitlist_position',),
            'classes': ('collapse',),
        }),
        ('Fees', {
            'fields': ('no_show_fee_charged',),
        }),
    )

    def status_badge(self, obj):
        colours = {
            'confirmed': '#10b981',
            'waitlisted': '#f59e0b',
            'cancelled': '#6b7280',
            'attended': '#3b82f6',
            'no_show': '#ef4444',
            'late_cancel': '#dc2626',
        }
        colour = colours.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            colour, obj.get_status_display(),
        )
    status_badge.short_description = 'Status'


# ---------------------------------------------------------------------------
# Appointment
# ---------------------------------------------------------------------------

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        'scheduled_at', 'member', 'staff', 'appointment_type',
        'duration_minutes', 'status_badge',
    )
    list_filter = ('appointment_type', 'status')
    search_fields = (
        'member__user__first_name', 'member__user__last_name',
        'staff__first_name', 'staff__last_name',
    )
    ordering = ('-scheduled_at',)
    date_hierarchy = 'scheduled_at'

    fieldsets = (
        ('Appointment', {
            'fields': (
                'member', 'staff', 'appointment_type',
                'scheduled_at', 'duration_minutes', 'status',
            ),
        }),
        ('Post-session Notes', {
            'fields': ('notes_after',),
            'classes': ('collapse',),
        }),
    )

    def status_badge(self, obj):
        colours = {
            'pending': '#f59e0b',
            'confirmed': '#10b981',
            'completed': '#3b82f6',
            'cancelled': '#6b7280',
        }
        colour = colours.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            colour, obj.get_status_display(),
        )
    status_badge.short_description = 'Status'


# ---------------------------------------------------------------------------
# WorkoutPlan
# ---------------------------------------------------------------------------

@admin.register(WorkoutPlan)
class WorkoutPlanAdmin(admin.ModelAdmin):
    list_display = (
        'created_at', 'member', 'source_badge', 'status_badge',
        'created_by', 'approved_at',
    )
    list_filter = ('source', 'status')
    search_fields = (
        'member__user__first_name', 'member__user__last_name',
        'created_by__first_name', 'created_by__last_name',
    )
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'approved_at')

    fieldsets = (
        ('Plan', {
            'fields': ('member', 'source', 'status', 'created_by', 'created_at', 'approved_at'),
        }),
        ('Plan Data', {
            'fields': ('plan_data',),
        }),
    )

    def source_badge(self, obj):
        colour = '#8b5cf6' if obj.source == 'ai' else '#0891b2'
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            colour, obj.get_source_display(),
        )
    source_badge.short_description = 'Source'

    def status_badge(self, obj):
        colours = {
            'draft': '#f59e0b',
            'approved': '#10b981',
            'active': '#3b82f6',
            'archived': '#6b7280',
        }
        colour = colours.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            colour, obj.get_status_display(),
        )
    status_badge.short_description = 'Status'

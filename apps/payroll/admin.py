from django.contrib import admin
from django.utils.html import format_html

from .models import StaffPayRate, PayrollPeriod


@admin.register(StaffPayRate)
class StaffPayRateAdmin(admin.ModelAdmin):
    list_display = (
        'staff', 'pay_type', 'rate', 'location',
        'effective_from', 'effective_to', 'is_current',
    )
    list_filter = ('pay_type', 'location')
    search_fields = ('staff__first_name', 'staff__last_name', 'staff__email')
    ordering = ('-effective_from',)

    fieldsets = (
        ('Staff', {
            'fields': ('staff', 'location'),
        }),
        ('Rate', {
            'fields': ('pay_type', 'rate', 'notes'),
        }),
        ('Effective Period', {
            'fields': ('effective_from', 'effective_to'),
        }),
    )

    def is_current(self, obj):
        if obj.is_current:
            return format_html('<span style="color:#10b981;font-weight:600">Yes</span>')
        return format_html('<span style="color:#6b7280">No</span>')
    is_current.short_description = 'Current?'


@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(admin.ModelAdmin):
    list_display = (
        'period_start', 'period_end', 'status_badge',
        'staff_count', 'total_payout', 'approved_by', 'approved_at',
    )
    list_filter = ('status',)
    ordering = ('-period_end',)
    readonly_fields = ('created_at',)
    date_hierarchy = 'period_end'

    fieldsets = (
        ('Period', {
            'fields': ('period_start', 'period_end', 'status', 'notes'),
        }),
        ('Summary', {
            'fields': ('summary', 'total_payout'),
            'description': (
                'JSON keyed by staff_id: '
                '{"name": "...", "hours": 40, "classes": 12, "total": 850.00}'
            ),
        }),
        ('Approval', {
            'fields': ('approved_by', 'approved_at'),
        }),
        ('Meta', {
            'fields': ('created_at',),
        }),
    )

    def status_badge(self, obj):
        colours = {
            'draft': '#6b7280',
            'approved': '#3b82f6',
            'paid': '#10b981',
        }
        colour = colours.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            colour, obj.get_status_display(),
        )
    status_badge.short_description = 'Status'

    def staff_count(self, obj):
        return obj.staff_count
    staff_count.short_description = 'Staff'

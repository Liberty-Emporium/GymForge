from django.contrib import admin
from django.utils.html import format_html

from .models import Lead, LeadFollowUp


class LeadFollowUpInline(admin.TabularInline):
    model = LeadFollowUp
    extra = 0
    fields = ('scheduled_at', 'method', 'completed_at', 'completed_by', 'notes')
    readonly_fields = ('completed_at',)


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = (
        'full_name', 'email', 'phone', 'source', 'status_badge',
        'assigned_to', 'location', 'created_at', 'last_contacted_at',
    )
    list_filter = ('status', 'source', 'location')
    search_fields = ('first_name', 'last_name', 'email', 'phone')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)
    inlines = [LeadFollowUpInline]

    fieldsets = (
        ('Contact', {
            'fields': ('first_name', 'last_name', 'email', 'phone'),
        }),
        ('Lead Details', {
            'fields': ('source', 'status', 'location', 'assigned_to', 'notes'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'last_contacted_at', 'converted_at'),
        }),
    )

    def status_badge(self, obj):
        colours = {
            'new': '#6b7280',
            'contacted': '#3b82f6',
            'trial_booked': '#f59e0b',
            'converted': '#10b981',
            'lost': '#ef4444',
        }
        colour = colours.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            colour, obj.get_status_display(),
        )
    status_badge.short_description = 'Status'


@admin.register(LeadFollowUp)
class LeadFollowUpAdmin(admin.ModelAdmin):
    list_display = ('lead', 'scheduled_at', 'method', 'is_completed', 'completed_by')
    list_filter = ('method',)
    search_fields = ('lead__first_name', 'lead__last_name', 'lead__email')
    ordering = ('scheduled_at',)

    def is_completed(self, obj):
        if obj.is_completed:
            return format_html('<span style="color:#10b981;font-weight:600">Done</span>')
        return format_html('<span style="color:#f59e0b;font-weight:600">Pending</span>')
    is_completed.short_description = 'Done?'

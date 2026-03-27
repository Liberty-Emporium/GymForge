from django.contrib import admin
from django.utils.html import format_html

from .models import Equipment, MaintenanceTicket, SupplyItem, SupplyRequest


# ---------------------------------------------------------------------------
# Equipment
# ---------------------------------------------------------------------------

class MaintenanceTicketInline(admin.TabularInline):
    model = MaintenanceTicket
    extra = 0
    fields = ('title', 'priority', 'status', 'reported_by', 'created_at')
    readonly_fields = ('created_at',)
    show_change_link = True


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'location', 'condition_badge', 'last_serviced',
        'next_service_due', 'service_overdue', 'is_active',
    )
    list_filter = ('condition', 'location', 'is_active')
    search_fields = ('name', 'serial_number', 'description')
    ordering = ('location', 'name')
    readonly_fields = ('created_at',)
    inlines = [MaintenanceTicketInline]

    fieldsets = (
        ('Equipment', {
            'fields': ('name', 'description', 'location', 'image', 'is_active'),
        }),
        ('Details', {
            'fields': ('serial_number', 'purchase_date', 'purchase_price', 'condition'),
        }),
        ('Servicing', {
            'fields': ('last_serviced', 'next_service_due', 'notes'),
        }),
        ('Meta', {
            'fields': ('created_at',),
        }),
    )

    def condition_badge(self, obj):
        colours = {
            'excellent': '#10b981',
            'good': '#3b82f6',
            'fair': '#f59e0b',
            'poor': '#ef4444',
            'out_of_service': '#111827',
        }
        colour = colours.get(obj.condition, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            colour, obj.get_condition_display(),
        )
    condition_badge.short_description = 'Condition'

    def service_overdue(self, obj):
        if obj.is_service_overdue:
            return format_html('<span style="color:#ef4444;font-weight:600">Overdue</span>')
        return format_html('<span style="color:#10b981">OK</span>')
    service_overdue.short_description = 'Service'


# ---------------------------------------------------------------------------
# MaintenanceTicket
# ---------------------------------------------------------------------------

@admin.register(MaintenanceTicket)
class MaintenanceTicketAdmin(admin.ModelAdmin):
    list_display = (
        'created_at', 'title', 'priority_badge', 'status_badge',
        'equipment', 'location', 'assigned_to', 'resolved_at',
    )
    list_filter = ('priority', 'status', 'location')
    search_fields = ('title', 'description', 'equipment__name')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Ticket', {
            'fields': ('title', 'description', 'photo', 'equipment', 'location'),
        }),
        ('Assignment', {
            'fields': ('priority', 'status', 'reported_by', 'assigned_to'),
        }),
        ('Resolution', {
            'fields': ('resolution_notes', 'resolved_at'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def priority_badge(self, obj):
        colours = {
            'low': '#6b7280',
            'medium': '#3b82f6',
            'high': '#f59e0b',
            'urgent': '#ef4444',
        }
        colour = colours.get(obj.priority, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            colour, obj.get_priority_display(),
        )
    priority_badge.short_description = 'Priority'

    def status_badge(self, obj):
        colours = {
            'open': '#ef4444',
            'in_progress': '#f59e0b',
            'pending_parts': '#3b82f6',
            'resolved': '#10b981',
            'closed': '#6b7280',
        }
        colour = colours.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            colour, obj.get_status_display(),
        )
    status_badge.short_description = 'Status'


# ---------------------------------------------------------------------------
# SupplyItem
# ---------------------------------------------------------------------------

class SupplyRequestInline(admin.TabularInline):
    model = SupplyRequest
    extra = 0
    fields = ('quantity', 'status', 'requested_by', 'created_at')
    readonly_fields = ('created_at',)
    show_change_link = True


@admin.register(SupplyItem)
class SupplyItemAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'category', 'location', 'current_stock',
        'minimum_stock', 'stock_status', 'unit', 'is_active',
    )
    list_filter = ('category', 'location', 'is_active')
    search_fields = ('name', 'supplier')
    ordering = ('category', 'name')
    inlines = [SupplyRequestInline]

    fieldsets = (
        ('Item', {
            'fields': ('name', 'description', 'category', 'location', 'is_active'),
        }),
        ('Stock', {
            'fields': ('unit', 'current_stock', 'minimum_stock', 'reorder_quantity', 'last_restocked'),
        }),
        ('Supplier', {
            'fields': ('supplier', 'unit_cost'),
        }),
    )

    def stock_status(self, obj):
        if obj.current_stock == 0:
            return format_html('<span style="color:#ef4444;font-weight:600">Empty</span>')
        if obj.is_low_stock:
            return format_html('<span style="color:#f59e0b;font-weight:600">Low</span>')
        return format_html('<span style="color:#10b981;font-weight:600">OK</span>')
    stock_status.short_description = 'Stock'


# ---------------------------------------------------------------------------
# SupplyRequest
# ---------------------------------------------------------------------------

@admin.register(SupplyRequest)
class SupplyRequestAdmin(admin.ModelAdmin):
    list_display = (
        'supply_item', 'quantity', 'status_badge',
        'requested_by', 'approved_by', 'created_at',
    )
    list_filter = ('status',)
    search_fields = ('supply_item__name', 'requested_by__first_name', 'requested_by__last_name')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Request', {
            'fields': ('supply_item', 'quantity', 'notes'),
        }),
        ('Workflow', {
            'fields': ('status', 'requested_by', 'approved_by', 'received_at'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def status_badge(self, obj):
        colours = {
            'pending': '#f59e0b',
            'approved': '#3b82f6',
            'ordered': '#8b5cf6',
            'received': '#10b981',
            'rejected': '#ef4444',
        }
        colour = colours.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            colour, obj.get_status_display(),
        )
    status_badge.short_description = 'Status'

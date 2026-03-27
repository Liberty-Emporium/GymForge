from django.contrib import admin
from django.utils.html import format_html

from .models import ShopProduct, ShopOrder


@admin.register(ShopProduct)
class ShopProductAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'category', 'price', 'stock', 'stock_badge',
        'loyalty_points_earned', 'is_active',
    )
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'sku', 'description')
    ordering = ('category', 'name')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Product', {
            'fields': ('name', 'description', 'category', 'sku', 'image'),
        }),
        ('Pricing & Stock', {
            'fields': ('price', 'stock', 'is_active'),
        }),
        ('Loyalty', {
            'fields': ('loyalty_points_earned',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def stock_badge(self, obj):
        if obj.stock == 0:
            return format_html(
                '<span style="color:#ef4444;font-weight:600">Out of stock</span>'
            )
        if obj.stock <= 5:
            return format_html(
                '<span style="color:#f59e0b;font-weight:600">Low ({})</span>',
                obj.stock,
            )
        return format_html(
            '<span style="color:#10b981;font-weight:600">In stock ({})</span>',
            obj.stock,
        )
    stock_badge.short_description = 'Stock status'


@admin.register(ShopOrder)
class ShopOrderAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'member', 'total_amount', 'payment_method',
        'status_badge', 'item_count', 'ordered_at',
    )
    list_filter = ('status', 'payment_method')
    search_fields = ('member__user__first_name', 'member__user__last_name')
    ordering = ('-ordered_at',)
    readonly_fields = ('ordered_at',)

    fieldsets = (
        ('Order', {
            'fields': ('member', 'processed_by', 'status', 'notes'),
        }),
        ('Items & Payment', {
            'fields': ('items', 'total_amount', 'payment_method', 'stripe_payment_intent'),
        }),
        ('Loyalty', {
            'fields': ('loyalty_points_used', 'loyalty_points_earned'),
        }),
        ('Timestamps', {
            'fields': ('ordered_at',),
        }),
    )

    def status_badge(self, obj):
        colours = {
            'pending': '#f59e0b',
            'completed': '#10b981',
            'refunded': '#3b82f6',
            'cancelled': '#ef4444',
        }
        colour = colours.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            colour, obj.get_status_display(),
        )
    status_badge.short_description = 'Status'

    def item_count(self, obj):
        return obj.item_count
    item_count.short_description = 'Items'

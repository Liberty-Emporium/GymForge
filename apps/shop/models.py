from django.db import models
from django.conf import settings


class ShopProduct(models.Model):
    CATEGORY_CHOICES = [
        ('supplement', 'Supplement'),
        ('apparel', 'Apparel'),
        ('equipment', 'Equipment'),
        ('food', 'Food & Drink'),
        ('accessory', 'Accessory'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    price = models.DecimalField(max_digits=8, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=100, blank=True)
    image = models.ImageField(upload_to='shop/products/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    loyalty_points_earned = models.PositiveIntegerField(
        default=0,
        help_text='Loyalty points awarded to the member when this product is purchased.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return f'{self.name} (${self.price})'

    @property
    def is_in_stock(self):
        return self.stock > 0


class ShopOrder(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('refunded', 'Refunded'),
        ('cancelled', 'Cancelled'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('card', 'Card'),
        ('tab', 'Member Tab'),
        ('cash', 'Cash'),
        ('loyalty', 'Loyalty Points'),
        ('stripe', 'Stripe'),
    ]

    member = models.ForeignKey(
        'members.MemberProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='shop_orders',
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_orders',
    )
    # JSON format: [{"product_id": 1, "name": "...", "qty": 2, "price": 25.00}]
    items = models.JSONField(default=list)
    total_amount = models.DecimalField(max_digits=8, decimal_places=2)
    payment_method = models.CharField(
        max_length=10, choices=PAYMENT_METHOD_CHOICES, default='card'
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    stripe_payment_intent = models.CharField(max_length=255, blank=True)
    loyalty_points_used = models.PositiveIntegerField(default=0)
    loyalty_points_earned = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    ordered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-ordered_at']

    def __str__(self):
        member_str = str(self.member) if self.member else 'Guest'
        return f'Order #{self.pk} — {member_str} ${self.total_amount}'

    @property
    def item_count(self):
        return sum(item.get('qty', 1) for item in self.items)

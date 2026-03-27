from django.db import models
from django.conf import settings


class Equipment(models.Model):
    """A piece of gym equipment tracked for maintenance purposes."""

    CONDITION_CHOICES = [
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('out_of_service', 'Out of Service'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.ForeignKey(
        'core.Location',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='equipment',
    )
    serial_number = models.CharField(max_length=100, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    purchase_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    condition = models.CharField(
        max_length=20, choices=CONDITION_CHOICES, default='good'
    )
    last_serviced = models.DateField(null=True, blank=True)
    next_service_due = models.DateField(null=True, blank=True)
    image = models.ImageField(upload_to='inventory/equipment/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['location', 'name']
        verbose_name_plural = 'equipment'

    def __str__(self):
        return f'{self.name} ({self.get_condition_display()})'

    @property
    def is_service_overdue(self):
        if not self.next_service_due:
            return False
        from django.utils import timezone
        return self.next_service_due < timezone.now().date()


class MaintenanceTicket(models.Model):
    """A reported issue or scheduled maintenance job for a piece of equipment."""

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('pending_parts', 'Pending Parts'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]

    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets',
    )
    location = models.ForeignKey(
        'core.Location',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='maintenance_tickets',
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reported_tickets',
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tickets',
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='open')
    photo = models.ImageField(upload_to='inventory/tickets/', blank=True, null=True)
    resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.get_priority_display()}] {self.title} — {self.get_status_display()}'

    @property
    def is_open(self):
        return self.status in ('open', 'in_progress', 'pending_parts')


class SupplyItem(models.Model):
    """A consumable supply item tracked in inventory."""

    CATEGORY_CHOICES = [
        ('cleaning', 'Cleaning'),
        ('towels', 'Towels & Linen'),
        ('toiletries', 'Toiletries'),
        ('office', 'Office'),
        ('equipment_parts', 'Equipment Parts'),
        ('first_aid', 'First Aid'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    location = models.ForeignKey(
        'core.Location',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supply_items',
    )
    unit = models.CharField(
        max_length=50,
        default='units',
        help_text='e.g. rolls, litres, boxes',
    )
    current_stock = models.PositiveIntegerField(default=0)
    minimum_stock = models.PositiveIntegerField(
        default=0,
        help_text='Alert threshold — triggers low-stock warning when current_stock falls below this.',
    )
    reorder_quantity = models.PositiveIntegerField(default=0)
    supplier = models.CharField(max_length=200, blank=True)
    unit_cost = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    last_restocked = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return f'{self.name} ({self.current_stock} {self.unit})'

    @property
    def is_low_stock(self):
        return self.current_stock <= self.minimum_stock


class SupplyRequest(models.Model):
    """A staff request to reorder or restock a supply item."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('ordered', 'Ordered'),
        ('received', 'Received'),
        ('rejected', 'Rejected'),
    ]

    supply_item = models.ForeignKey(
        SupplyItem,
        on_delete=models.CASCADE,
        related_name='requests',
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supply_requests',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_supply_requests',
    )
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    received_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return (
            f'{self.supply_item.name} x{self.quantity} '
            f'({self.get_status_display()})'
        )

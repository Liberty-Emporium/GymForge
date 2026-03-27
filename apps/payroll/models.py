from django.db import models
from django.conf import settings


class StaffPayRate(models.Model):
    """Defines the pay rates for a staff member."""

    PAY_TYPE_CHOICES = [
        ('hourly', 'Hourly'),
        ('salary', 'Salary'),
        ('per_class', 'Per Class'),
        ('commission', 'Commission'),
    ]

    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pay_rates',
    )
    pay_type = models.CharField(max_length=15, choices=PAY_TYPE_CHOICES, default='hourly')
    rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text='Hourly rate, annual salary, per-class fee, or commission %.',
    )
    location = models.ForeignKey(
        'core.Location',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pay_rates',
        help_text='Leave blank to apply across all locations.',
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-effective_from']

    def __str__(self):
        return (
            f'{self.staff.get_full_name() or self.staff.username} — '
            f'{self.get_pay_type_display()} ${self.rate}'
        )

    @property
    def is_current(self):
        from django.utils import timezone
        today = timezone.now().date()
        if self.effective_from > today:
            return False
        if self.effective_to and self.effective_to < today:
            return False
        return True


class PayrollPeriod(models.Model):
    """A closed payroll run covering a date range."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
    ]

    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    # JSON format:
    # {
    #   "<staff_id>": {
    #     "name": "Jane Smith",
    #     "hours": 40,
    #     "classes": 12,
    #     "total": 850.00
    #   }
    # }
    summary = models.JSONField(
        default=dict,
        help_text=(
            'Keyed by staff_id. Each entry: '
            '{"name": "...", "hours": 40, "classes": 12, "total": 850.00}'
        ),
    )
    total_payout = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_payroll_periods',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-period_end']

    def __str__(self):
        return f'Payroll {self.period_start} – {self.period_end} ({self.get_status_display()})'

    @property
    def staff_count(self):
        return len(self.summary)

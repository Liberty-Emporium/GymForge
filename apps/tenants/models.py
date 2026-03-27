from django_tenants.models import TenantMixin, DomainMixin
from django.db import models
from django.utils import timezone


class GymTenant(TenantMixin):
    """
    One row per gym. Lives in the PUBLIC schema (SHARED_APPS).

    django-tenants uses this model to:
      - route every inbound request to the correct PostgreSQL schema
      - auto-create a new schema on save (auto_create_schema = True)

    Subscription states
    -------------------
    trial       → newly provisioned; 14-day free period, no card required
    active      → paid subscription confirmed via Stripe webhook
    suspended   → trial expired or payment failed; portals locked
    cancelled   → owner cancelled; data held for 30 days then purged

    Business rules (see also GymAccessMiddleware):
      - member_app_active is ONLY set True when subscription_status = 'active'
      - trial_active is flipped False by GymAccessMiddleware on day 14
      - data_retention_until is set by a Celery task on cancellation (Step 44)

    Note on plan FK
    ---------------
    GymTenant.plan points to billing.Plan (the GymForge SaaS tier — Starter /
    Growth / Pro). billing.Plan is added to SHARED_APPS in Step 5 so this FK
    resolves in the public schema.
    """

    gym_name = models.CharField(max_length=200)
    owner_email = models.EmailField()

    # SaaS plan this gym is on (Starter / Growth / Pro)
    # Plan lives in apps.platform_admin (SHARED_APPS → public schema)
    plan = models.ForeignKey(
        'platform_admin.Plan',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='tenants',
    )

    trial_start_date = models.DateTimeField(auto_now_add=True)
    trial_active = models.BooleanField(default=True)
    # Day numbers for which trial emails have already been sent — prevents re-sends on retry.
    # e.g. [0, 3, 7] — appended on each successful send; never removed.
    trial_emails_sent = models.JSONField(default=list)

    SUBSCRIPTION_STATUSES = [
        ('trial', 'Trial'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('cancelled', 'Cancelled'),
    ]
    subscription_status = models.CharField(
        max_length=20,
        choices=SUBSCRIPTION_STATUSES,
        default='trial',
        db_index=True,
    )

    # Locked until the gym subscribes and activates (billing webhook sets this)
    member_app_active = models.BooleanField(default=False)

    # Stripe identifiers — populated after the gym owner subscribes
    stripe_customer_id = models.CharField(max_length=100, blank=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True)

    # Set on cancellation; schema purged after this date by Celery (Step 44)
    data_retention_until = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    # django-tenants auto-creates the PostgreSQL schema when this row is saved
    auto_create_schema = True

    class Meta:
        verbose_name = 'Gym Tenant'
        verbose_name_plural = 'Gym Tenants'

    def __str__(self):
        return f'{self.gym_name} ({self.schema_name})'

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def trial_days_remaining(self):
        """Days left in the 14-day trial. Negative means expired."""
        elapsed = (timezone.now() - self.trial_start_date).days
        return 14 - elapsed

    @property
    def is_accessible(self):
        """True if the gym's portals should be open."""
        return self.trial_active or self.subscription_status == 'active'

    def activate_subscription(self, stripe_customer_id, stripe_subscription_id):
        """Called by the Stripe webhook (Step 47) once payment is confirmed."""
        self.stripe_customer_id = stripe_customer_id
        self.stripe_subscription_id = stripe_subscription_id
        self.subscription_status = 'active'
        self.trial_active = False
        self.member_app_active = True
        self.save(update_fields=[
            'stripe_customer_id',
            'stripe_subscription_id',
            'subscription_status',
            'trial_active',
            'member_app_active',
        ])

    def suspend(self):
        """Suspend access — payment failure or trial expiry."""
        self.subscription_status = 'suspended'
        self.member_app_active = False
        self.save(update_fields=['subscription_status', 'member_app_active'])

    def cancel(self, retention_days=30):
        """Cancel subscription; schema purged after retention_days (Step 44)."""
        from datetime import timedelta
        self.subscription_status = 'cancelled'
        self.member_app_active = False
        self.data_retention_until = timezone.now() + timedelta(days=retention_days)
        self.save(update_fields=[
            'subscription_status',
            'member_app_active',
            'data_retention_until',
        ])


class GymDomain(DomainMixin):
    """
    Maps a domain/subdomain to a GymTenant.

    Primary domain  : ironhouse.gymforge.com  (is_primary=True)
    Custom domain   : members.ironhouse.com   (is_primary=False, same tenant)

    django-tenants resolves the correct GymTenant from each inbound
    request's HOST header by looking up GymDomain.domain.
    """

    class Meta:
        verbose_name = 'Gym Domain'
        verbose_name_plural = 'Gym Domains'

    def __str__(self):
        marker = ' [primary]' if self.is_primary else ''
        return f'{self.domain}{marker} → {self.tenant.gym_name}'

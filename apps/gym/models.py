"""
apps.gym — Single-tenant gym configuration.

Replaces apps.tenants (django-tenants multi-tenant model).
There is exactly ONE GymConfig row per deployment.
All subscription/billing state lives here instead of on a tenant object.
"""
from django.db import models
from django.utils import timezone


class GymConfig(models.Model):
    """
    Single-row table holding the gym's identity, branding, and subscription state.

    Subscription states
    -------------------
    trial       → setup complete; 14-day free period
    active      → Stripe subscription confirmed
    suspended   → trial expired or payment failed
    cancelled   → owner cancelled

    Access is enforced by apps.accounts.middleware.GymAccessMiddleware.
    """

    SUBSCRIPTION_STATUSES = [
        ('trial', 'Trial'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('cancelled', 'Cancelled'),
    ]

    gym_name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True, help_text='URL-safe gym identifier')
    owner_email = models.EmailField()

    # Subscription
    subscription_status = models.CharField(
        max_length=20, choices=SUBSCRIPTION_STATUSES, default='trial', db_index=True,
    )
    trial_start_date = models.DateTimeField(auto_now_add=True)
    trial_active = models.BooleanField(default=True)
    member_app_active = models.BooleanField(default=False)

    # Stripe
    stripe_customer_id = models.CharField(max_length=100, blank=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Gym Config'
        verbose_name_plural = 'Gym Config'

    def __str__(self):
        return f'{self.gym_name} [{self.subscription_status}]'

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def get(cls):
        """Return the single GymConfig row (or None if setup not run yet)."""
        return cls.objects.first()

    @property
    def trial_days_remaining(self):
        elapsed = (timezone.now() - self.trial_start_date).days
        return max(0, 14 - elapsed)

    @property
    def is_accessible(self):
        return self.trial_active or self.subscription_status == 'active'

    def activate_subscription(self, stripe_customer_id, stripe_subscription_id):
        self.stripe_customer_id = stripe_customer_id
        self.stripe_subscription_id = stripe_subscription_id
        self.subscription_status = 'active'
        self.trial_active = False
        self.member_app_active = True
        self.save()

    def suspend(self):
        self.subscription_status = 'suspended'
        self.member_app_active = False
        self.save()

    def cancel(self):
        self.subscription_status = 'cancelled'
        self.member_app_active = False
        self.save()

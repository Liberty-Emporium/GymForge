from django.db import models


# Plan has moved to apps.platform_admin (SHARED_APPS) so it lives in the
# public schema and GymTenant.plan FK resolves correctly without pulling
# all of apps.billing into SHARED_APPS.


# ---------------------------------------------------------------------------
# MembershipTier — TENANT SCHEMA
# The gym's own plans: what members pay the gym.
# ---------------------------------------------------------------------------

class MembershipTier(models.Model):
    """
    A membership plan offered by the gym to its members.

    Defined by the gym owner in Step 4 of the setup wizard and managed
    in the Owner portal. Linked to Services via ManyToMany.

    Cancellation / no-show policy fields are enforced at booking time
    (apps/scheduling) and at the Celery no-show task (Step 43).
    """

    BILLING_CYCLES = [
        ('monthly', 'Monthly'),
        ('annual', 'Annual'),
        ('drop_in', 'Drop-in'),
        ('free', 'Free'),
    ]

    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CYCLES)
    description = models.TextField(blank=True)
    included_services = models.ManyToManyField('core.Service', blank=True)
    is_active = models.BooleanField(default=True)
    trial_days = models.IntegerField(default=0)

    # Cancellation policy — enforced per booking
    cancellation_window_hours = models.IntegerField(
        default=2,
        help_text='How many hours before class start a member can cancel for free.',
    )
    no_show_fee = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0.00,
        help_text='Charged immediately via Stripe when a member no-shows.',
    )
    late_cancel_fee = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0.00,
        help_text='Charged when a member cancels inside the cancellation window.',
    )

    class Meta:
        ordering = ['price']
        verbose_name = 'Membership Tier'
        verbose_name_plural = 'Membership Tiers'

    def __str__(self):
        return f'{self.name} — {self.get_billing_cycle_display()} (${self.price})'


# ---------------------------------------------------------------------------
# MemberMembership — TENANT SCHEMA
# A member's active subscription to a MembershipTier.
# ---------------------------------------------------------------------------

class MemberMembership(models.Model):
    """
    Tracks a member's current (or historical) subscription.

    One active row per member at any time. Status transitions:
      active → expiring      (renewal imminent)
      active → overdue       (Stripe payment failed; grace period starts)
      overdue → suspended    (grace period elapsed with no payment)
      active/overdue → frozen (member requested freeze)
      active → cancelled     (member or owner cancelled)

    Door access (RFID) is revoked within 60 seconds of overdue/suspended
    status via a Celery task (Step 43 business rule).
    """

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expiring', 'Expiring Soon'),
        ('overdue', 'Payment Overdue'),
        ('suspended', 'Suspended'),
        ('cancelled', 'Cancelled'),
        ('frozen', 'Frozen'),
    ]

    member = models.ForeignKey(
        'members.MemberProfile',
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    tier = models.ForeignKey(
        MembershipTier,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        db_index=True,
    )
    stripe_subscription_id = models.CharField(max_length=100, blank=True)
    stripe_customer_id = models.CharField(max_length=100, blank=True)
    grace_period_days = models.IntegerField(
        default=3,
        help_text='Days after payment failure before status moves to suspended.',
    )
    overdue_since = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-start_date']
        verbose_name = 'Member Membership'
        verbose_name_plural = 'Member Memberships'

    def __str__(self):
        return (
            f'{self.member.user.get_full_name()} — '
            f'{self.tier.name} [{self.status}]'
        )

    @property
    def is_active(self):
        return self.status == 'active'

    @property
    def allows_access(self):
        """True if the member should be let through the door."""
        return self.status in ('active', 'expiring', 'frozen')


# ---------------------------------------------------------------------------
# MemberTab — TENANT SCHEMA
# Running purchase balance charged at billing cycle.
# ---------------------------------------------------------------------------

class MemberTab(models.Model):
    """
    A running tab for POS purchases (protein bars, supplements, merch, etc.)
    charged to the member's payment method at the end of the billing cycle.

    Created automatically when a member makes their first tab purchase.
    spending_limit defaults to $100; gym owner can adjust per member.
    """

    member = models.OneToOneField(
        'members.MemberProfile',
        on_delete=models.CASCADE,
        related_name='tab',
    )
    balance = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    spending_limit = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=100.00,
    )
    last_charged = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Member Tab'
        verbose_name_plural = 'Member Tabs'

    def __str__(self):
        return (
            f'{self.member.user.get_full_name()} — '
            f'${self.balance} / ${self.spending_limit}'
        )

    @property
    def is_over_limit(self):
        return self.balance >= self.spending_limit


# ---------------------------------------------------------------------------
# CardPurchase — TENANT SCHEMA
# POS transaction via RFID card tap at a DoorDevice(type='pos').
# ---------------------------------------------------------------------------

class CardPurchase(models.Model):
    """
    A single point-of-sale transaction triggered by an RFID card tap.

    Processed immediately via Stripe PaymentIntent. If the member has a
    MemberTab open, the charge may be deferred and added to tab.balance.

    Loyalty points are awarded at the time of purchase (5 pts per $1 spent
    by default — configurable via LoyaltyRule).
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    card = models.ForeignKey(
        'checkin.MemberCard',
        on_delete=models.CASCADE,
        related_name='purchases',
    )
    device = models.ForeignKey(
        'checkin.DoorDevice',
        on_delete=models.CASCADE,
        related_name='purchases',
    )
    item_description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    processed_at = models.DateTimeField(auto_now_add=True)
    stripe_payment_intent = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='completed',
    )

    class Meta:
        ordering = ['-processed_at']
        verbose_name = 'Card Purchase'
        verbose_name_plural = 'Card Purchases'

    def __str__(self):
        return (
            f'{self.card.member.user.get_full_name()} — '
            f'{self.item_description} ${self.amount} [{self.status}]'
        )


# ---------------------------------------------------------------------------
# NoShowCharge — TENANT SCHEMA
# Stripe charge issued when a member no-shows or late-cancels a class.
# ---------------------------------------------------------------------------

class NoShowCharge(models.Model):
    """
    Records a no-show or late-cancellation fee charged via Stripe.

    Created by the process_no_shows Celery task (Step 43), which runs
    every 15 minutes and scans for Booking rows where:
      - class_session.end_datetime < now - 30min
      - status is still 'confirmed'

    Business rule (Section 17): no-show fees charge immediately to Stripe.
    No tab, no delay.
    """

    CHARGE_TYPES = [
        ('no_show', 'No Show'),
        ('late_cancel', 'Late Cancel'),
    ]

    member = models.ForeignKey(
        'members.MemberProfile',
        on_delete=models.CASCADE,
        related_name='no_show_charges',
    )
    booking = models.ForeignKey(
        'scheduling.Booking',
        on_delete=models.CASCADE,
        related_name='no_show_charges',
    )
    amount = models.DecimalField(max_digits=6, decimal_places=2)
    charge_type = models.CharField(max_length=20, choices=CHARGE_TYPES)
    stripe_payment_intent = models.CharField(max_length=100, blank=True)
    charged_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='completed')

    class Meta:
        ordering = ['-charged_at']
        verbose_name = 'No-Show Charge'
        verbose_name_plural = 'No-Show Charges'

    def __str__(self):
        return (
            f'{self.member.user.get_full_name()} — '
            f'{self.get_charge_type_display()} ${self.amount} [{self.status}]'
        )

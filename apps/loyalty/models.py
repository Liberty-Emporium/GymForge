from django.db import models
from django.conf import settings


class LoyaltyRule(models.Model):
    """Defines how many points are awarded for a given action."""

    ACTION_CHOICES = [
        ('checkin', 'Check-in'),
        ('class_attended', 'Class Attended'),
        ('referral', 'Referral'),
        ('workout_logged', 'Workout Logged'),
        ('intake_completed', 'Intake Completed'),
        ('birthday', 'Birthday'),
        ('product_purchase', 'Product Purchase'),
        ('custom', 'Custom'),
    ]

    action = models.CharField(max_length=30, choices=ACTION_CHOICES, unique=True)
    points = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    max_per_day = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Cap how many times this rule can fire per member per day. Leave blank for unlimited.',
    )

    class Meta:
        ordering = ['action']

    def __str__(self):
        return f'{self.get_action_display()} — {self.points} pts'


class LoyaltyTransaction(models.Model):
    """Immutable ledger entry for every points credit or debit."""

    TRANSACTION_TYPE_CHOICES = [
        ('earn', 'Earned'),
        ('redeem', 'Redeemed'),
        ('expire', 'Expired'),
        ('adjust', 'Manual Adjustment'),
    ]

    member = models.ForeignKey(
        'members.MemberProfile',
        on_delete=models.CASCADE,
        related_name='loyalty_transactions',
    )
    points = models.IntegerField(help_text='Positive = credit, negative = debit')
    transaction_type = models.CharField(
        max_length=10, choices=TRANSACTION_TYPE_CHOICES, default='earn'
    )
    action = models.CharField(
        max_length=30,
        choices=LoyaltyRule.ACTION_CHOICES + [('redeem', 'Redemption'), ('adjust', 'Adjustment')],
        blank=True,
    )
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='loyalty_transactions_created',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        sign = '+' if self.points >= 0 else ''
        return f'{self.member} {sign}{self.points} pts ({self.get_transaction_type_display()})'


class LoyaltyReward(models.Model):
    """A reward that members can redeem points for."""

    REWARD_TYPE_CHOICES = [
        ('discount', 'Discount'),
        ('free_class', 'Free Class'),
        ('product', 'Product'),
        ('service', 'Service'),
        ('custom', 'Custom'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    reward_type = models.CharField(max_length=20, choices=REWARD_TYPE_CHOICES, default='custom')
    points_cost = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    stock = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Leave blank for unlimited stock.',
    )
    image = models.ImageField(upload_to='loyalty/rewards/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['points_cost', 'name']

    def __str__(self):
        return f'{self.name} ({self.points_cost} pts)'

    @property
    def is_available(self):
        if not self.is_active:
            return False
        if self.stock is not None and self.stock <= 0:
            return False
        return True


class BadgeMilestone(models.Model):
    """Defines a badge awarded when a member reaches a loyalty points threshold."""

    BADGE_TYPE_CHOICES = [
        ('points', 'Total Points'),
        ('checkins', 'Total Check-ins'),
        ('workouts', 'Total Workouts'),
        ('streak', 'Day Streak'),
        ('referrals', 'Total Referrals'),
        ('custom', 'Custom'),
    ]

    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    badge_type = models.CharField(max_length=20, choices=BADGE_TYPE_CHOICES, default='points')
    threshold = models.PositiveIntegerField(help_text='Value required to earn this badge')
    icon = models.ImageField(upload_to='loyalty/badges/', blank=True, null=True)
    points_reward = models.PositiveIntegerField(
        default=0,
        help_text='Bonus loyalty points awarded when this badge is unlocked.',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['badge_type', 'threshold']

    def __str__(self):
        return f'{self.name} ({self.get_badge_type_display()} ≥ {self.threshold})'


class MemberBadge(models.Model):
    """Records that a member has earned a specific badge milestone."""

    member = models.ForeignKey(
        'members.MemberProfile',
        on_delete=models.CASCADE,
        related_name='badges',
    )
    milestone = models.ForeignKey(
        BadgeMilestone,
        on_delete=models.CASCADE,
        related_name='earned_by',
    )
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('member', 'milestone')
        ordering = ['-earned_at']

    def __str__(self):
        return f'{self.member} earned {self.milestone.name}'

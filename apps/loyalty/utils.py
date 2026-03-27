"""
Loyalty Points Utility (Section 10)

award_loyalty_points() is the single entry point for crediting points to a member.
It:
  1. Looks up the active LoyaltyRule for the given action.
  2. Enforces the per-day cap if configured.
  3. Creates a LoyaltyTransaction ledger entry.
  4. Increments MemberProfile.loyalty_points atomically.
  5. Calls check_badge_milestones() to unlock any newly-reached badges.

Always call this function instead of mutating loyalty_points directly.
"""

from django.db import transaction
from django.db.models import F
from django.utils import timezone


def award_loyalty_points(member_profile, action, description='', created_by=None):
    """
    Award loyalty points to a member for the given action.

    Parameters
    ----------
    member_profile : MemberProfile
    action         : str  — must match a LoyaltyRule.action value
    description    : str  — optional human-readable note stored on the transaction
    created_by     : User — optional; the staff user who triggered the award

    Returns
    -------
    int  — points awarded (0 if rule inactive, not found, or capped)
    """
    from apps.loyalty.models import LoyaltyRule, LoyaltyTransaction

    try:
        rule = LoyaltyRule.objects.get(action=action, is_active=True)
    except LoyaltyRule.DoesNotExist:
        return 0

    if rule.points <= 0:
        return 0

    # Per-day cap check
    if rule.max_per_day is not None:
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = LoyaltyTransaction.objects.filter(
            member=member_profile,
            action=action,
            created_at__gte=today_start,
        ).count()
        if today_count >= rule.max_per_day:
            return 0

    with transaction.atomic():
        LoyaltyTransaction.objects.create(
            member=member_profile,
            points=rule.points,
            transaction_type='earn',
            action=action,
            description=description or rule.description,
            created_by=created_by,
        )

        # Atomic increment — avoids race conditions
        from apps.members.models import MemberProfile
        MemberProfile.objects.filter(pk=member_profile.pk).update(
            loyalty_points=F('loyalty_points') + rule.points
        )
        # Refresh in-memory instance so callers see the updated value
        member_profile.refresh_from_db(fields=['loyalty_points'])

    check_badge_milestones(member_profile)
    return rule.points


def check_badge_milestones(member_profile):
    """
    Check all active BadgeMilestones and award any the member has now reached
    but not yet received.

    Runs after every points award. Only 'points' type badges are evaluated here;
    other badge types (checkins, streak, etc.) should call this after updating
    the relevant counter.

    Parameters
    ----------
    member_profile : MemberProfile
    """
    from apps.loyalty.models import BadgeMilestone, MemberBadge, LoyaltyTransaction

    already_earned = set(
        MemberBadge.objects.filter(member=member_profile)
        .values_list('milestone_id', flat=True)
    )

    eligible = BadgeMilestone.objects.filter(
        is_active=True,
        badge_type='points',
        threshold__lte=member_profile.loyalty_points,
    ).exclude(pk__in=already_earned)

    for milestone in eligible:
        with transaction.atomic():
            MemberBadge.objects.get_or_create(member=member_profile, milestone=milestone)

            # Award bonus points if configured
            if milestone.points_reward > 0:
                LoyaltyTransaction.objects.create(
                    member=member_profile,
                    points=milestone.points_reward,
                    transaction_type='earn',
                    action='custom',
                    description=f'Badge unlocked: {milestone.name}',
                )
                from apps.members.models import MemberProfile
                MemberProfile.objects.filter(pk=member_profile.pk).update(
                    loyalty_points=F('loyalty_points') + milestone.points_reward
                )
                member_profile.refresh_from_db(fields=['loyalty_points'])

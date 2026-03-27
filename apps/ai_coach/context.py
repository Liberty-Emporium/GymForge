"""
AI Context Assembly

Builds the template variable dicts that are interpolated into the two
system prompt templates (Section 9) before being sent to Claude.

build_member_context(member_profile)  → dict for the Member AI Coach prompt
build_owner_context(owner_user)       → dict for the Owner AI Assistant prompt

These functions are deliberately import-heavy — they are called once per
conversation start, not per message, so the overhead is acceptable.
"""

from django.utils import timezone


# ---------------------------------------------------------------------------
# Member AI Coach context
# ---------------------------------------------------------------------------

def build_member_context(member_profile):
    """
    Assemble context variables for the Member AI Coach system prompt.

    Pulls from:
    - MemberProfile / User (name, loyalty, referral)
    - HealthProfile      (goals, health history, nutrition, training prefs)
    - WorkoutLog         (last 10 sessions → workout_summary)
    - CheckIn            (streak calculation)
    - GymProfile         (gym_name, gym_additional_context)
    - AISystemPrompt     (gym_additional_context layer)

    Returns a dict ready for str.format_map() against the member prompt template.
    """
    from apps.members.models import WorkoutLog
    from apps.core.models import GymProfile

    health = getattr(member_profile, 'healthprofile', None)

    # Last 10 workout sessions for the prompt summary
    recent_workouts = WorkoutLog.objects.filter(
        member=member_profile
    ).order_by('-workout_date')[:10]

    if recent_workouts:
        workout_summary = '\n'.join(
            f'- {w.workout_date}: {w.exercise_count} exercises, '
            f'{w.duration_minutes or "?"}min'
            for w in recent_workouts
        )
    else:
        workout_summary = 'No workouts logged yet.'

    try:
        gym_name = GymProfile.objects.get().gym_name
    except GymProfile.DoesNotExist:
        gym_name = 'the gym'

    return {
        'member_name': member_profile.user.get_full_name() or member_profile.user.username,
        'gym_name': gym_name,

        # Goals
        'fitness_goal': health.fitness_goal if health else 'Not set',
        'goal_detail': health.goal_detail if health else '',
        'activity_level': health.activity_level if health else 'Unknown',

        # Health history
        'injuries_limitations': (
            health.injuries_limitations if health else 'None reported'
        ),
        'medical_conditions': (
            health.medical_conditions if health else 'None reported'
        ),

        # Nutrition
        'dietary_preference': (
            health.dietary_preference if health else 'No preference'
        ),
        'food_allergies': health.food_allergies if health else 'None',
        'current_supplements': (
            health.current_supplements if health else 'None'
        ),

        # Training preferences
        'preferred_workout_time': (
            health.preferred_workout_time if health else 'No preference'
        ),
        'sleep_hours': health.sleep_hours if health else 'Unknown',
        'stress_level': health.stress_level if health else 'Unknown',

        # Activity summary
        'workout_summary': workout_summary,
        'goal_progress': _goal_progress_summary(member_profile),

        # Loyalty
        'loyalty_points': member_profile.loyalty_points,
        'streak_days': calculate_streak(member_profile),

        # Gym-owner additions to the system prompt
        'gym_additional_context': _get_gym_additional_context('member_coach'),
    }


# ---------------------------------------------------------------------------
# Owner AI Business Assistant context
# ---------------------------------------------------------------------------

def build_owner_context(owner_user):
    """
    Assemble context variables for the Owner AI Business Assistant prompt.

    Injects live gym metrics so the AI gives data-driven advice rather
    than generic guidance. All figures are current at the time the
    conversation starts (not cached between messages).

    Returns a dict ready for str.format_map() against the owner prompt template.
    """
    from apps.core.models import GymProfile, Location
    from apps.members.models import MemberProfile
    from apps.billing.models import MemberMembership
    from apps.checkin.models import CheckIn, MaintenanceTicket
    from apps.leads.models import Lead
    from apps.accounts.models import User
    from apps.scheduling.models import Booking, ClassSession

    try:
        gym_name = GymProfile.objects.get().gym_name
    except GymProfile.DoesNotExist:
        gym_name = 'the gym'

    location_names = ', '.join(
        Location.objects.filter(is_active=True).values_list('name', flat=True)
    ) or 'None set up yet'

    return {
        'owner_name': owner_user.get_full_name() or owner_user.username,
        'gym_name': gym_name,

        # Membership
        'member_count': MemberMembership.objects.filter(status='active').count(),
        'trial_member_count': MemberMembership.objects.filter(status__in=['active']).filter(
            tier__trial_days__gt=0
        ).count(),

        # Locations
        'location_names': location_names,

        # Churn risk (no check-in in 30+ days)
        'churn_risk_count': _get_churn_risk_count(),

        # Revenue
        'revenue_this_month': _get_revenue_this_month(),
        'revenue_last_month': _get_revenue_last_month(),
        'overdue_amount': _get_overdue_amount(),

        # Operations
        'open_tickets': _get_open_ticket_count(),
        'staff_count': User.objects.exclude(
            role__in=['member', 'platform_admin']
        ).count(),

        # Scheduling
        'top_class': _get_top_class(),
        'new_members': _get_new_members_this_month(),

        # Leads
        'leads_count': Lead.objects.exclude(
            status__in=['converted', 'lost']
        ).count(),

        # Loyalty
        'points_issued': _get_loyalty_points_this_month(),

        # Gym-owner additions to the system prompt
        'gym_additional_context': _get_gym_additional_context('owner_assistant'),
    }


# ---------------------------------------------------------------------------
# Streak calculation
# ---------------------------------------------------------------------------

def calculate_streak(member_profile):
    """
    Return the number of consecutive days the member has checked in,
    counting back from today.

    A streak is broken by any calendar day (excluding today) with no check-in.
    """
    from apps.checkin.models import CheckIn

    checkins = (
        CheckIn.objects
        .filter(member=member_profile)
        .values_list('checked_in_at', flat=True)
        .order_by('-checked_in_at')
    )

    if not checkins:
        return 0

    checked_dates = sorted(
        {ci.date() for ci in checkins},
        reverse=True,
    )

    today = timezone.now().date()
    streak = 0

    for i, date in enumerate(checked_dates):
        expected = today - timezone.timedelta(days=i)
        if date == expected:
            streak += 1
        else:
            break

    return streak


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _goal_progress_summary(member_profile):
    """Brief textual progress summary for the AI prompt."""
    from apps.members.models import BodyMetric, WorkoutLog

    workout_count = WorkoutLog.objects.filter(member=member_profile).count()
    latest_metric = (
        BodyMetric.objects
        .filter(member=member_profile)
        .order_by('-recorded_at')
        .first()
    )

    parts = [f'{workout_count} workouts logged total']
    if latest_metric:
        if latest_metric.weight_kg:
            parts.append(f'Last recorded weight: {latest_metric.weight_kg} kg')
        if latest_metric.body_fat_percent:
            parts.append(f'Body fat: {latest_metric.body_fat_percent}%')
    return '. '.join(parts) or 'No progress data yet.'


def _get_gym_additional_context(prompt_type):
    """
    Return the gym owner's additional context string for the given prompt type.
    Returns '' if no active AISystemPrompt exists.
    """
    from apps.ai_coach.models import AISystemPrompt

    try:
        prompt = AISystemPrompt.objects.get(prompt_type=prompt_type, is_active=True)
        return prompt.gym_additional_context or ''
    except AISystemPrompt.DoesNotExist:
        return ''


def _get_churn_risk_count():
    """Members with an active membership who have not checked in for 30+ days."""
    from apps.checkin.models import CheckIn
    from apps.billing.models import MemberMembership

    cutoff = timezone.now() - timezone.timedelta(days=30)
    active_member_ids = MemberMembership.objects.filter(
        status='active'
    ).values_list('member_id', flat=True)

    recent_checkin_ids = CheckIn.objects.filter(
        checked_in_at__gte=cutoff
    ).values_list('member_id', flat=True)

    return len(set(active_member_ids) - set(recent_checkin_ids))


def _get_revenue_this_month():
    """Sum of completed Stripe payments this calendar month (placeholder)."""
    # Full implementation in Step 47 (Stripe billing)
    # Returns a formatted string for the AI prompt
    from django.utils import timezone
    now = timezone.now()
    try:
        from apps.billing.models import CardPurchase
        from django.db.models import Sum
        total = CardPurchase.objects.filter(
            processed_at__year=now.year,
            processed_at__month=now.month,
            status='completed',
        ).aggregate(total=Sum('amount'))['total'] or 0
        return f'{total:,.2f}'
    except Exception:
        return '0.00'


def _get_revenue_last_month():
    """Sum of completed payments last calendar month."""
    from django.utils import timezone
    now = timezone.now()
    if now.month == 1:
        year, month = now.year - 1, 12
    else:
        year, month = now.year, now.month - 1
    try:
        from apps.billing.models import CardPurchase
        from django.db.models import Sum
        total = CardPurchase.objects.filter(
            processed_at__year=year,
            processed_at__month=month,
            status='completed',
        ).aggregate(total=Sum('amount'))['total'] or 0
        return f'{total:,.2f}'
    except Exception:
        return '0.00'


def _get_overdue_amount():
    """Total outstanding balance from overdue memberships."""
    # Full Stripe reconciliation in Step 47; return placeholder for now
    return '0.00'


def _get_open_ticket_count():
    """Count of open maintenance tickets."""
    try:
        from apps.inventory.models import MaintenanceTicket
        return MaintenanceTicket.objects.filter(status='open').count()
    except Exception:
        return 0


def _get_top_class():
    """Name of the class type with the most confirmed bookings this month."""
    from django.utils import timezone
    now = timezone.now()
    try:
        from apps.scheduling.models import Booking
        from django.db.models import Count
        top = (
            Booking.objects
            .filter(
                status__in=['confirmed', 'attended'],
                class_session__start_datetime__year=now.year,
                class_session__start_datetime__month=now.month,
            )
            .values('class_session__class_type__name')
            .annotate(total=Count('id'))
            .order_by('-total')
            .first()
        )
        return top['class_session__class_type__name'] if top else 'N/A'
    except Exception:
        return 'N/A'


def _get_new_members_this_month():
    """Members who joined this calendar month."""
    from django.utils import timezone
    now = timezone.now()
    try:
        from apps.members.models import MemberProfile
        return MemberProfile.objects.filter(
            join_date__year=now.year,
            join_date__month=now.month,
        ).count()
    except Exception:
        return 0


def _get_loyalty_points_this_month():
    """Total loyalty points issued this calendar month."""
    from django.utils import timezone
    now = timezone.now()
    try:
        from apps.loyalty.models import LoyaltyTransaction
        from django.db.models import Sum
        total = LoyaltyTransaction.objects.filter(
            created_at__year=now.year,
            created_at__month=now.month,
            points__gt=0,
        ).aggregate(total=Sum('points'))['total'] or 0
        return total
    except Exception:
        return 0

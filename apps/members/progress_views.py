"""
Member progress dashboard views (/app/progress/).

All views require role='member'. Mounted via apps/members/urls.py.
"""
import datetime
import json
from functools import wraps

from django.conf import settings
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.members.models import BodyMetric, MemberProfile


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def _member_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'{settings.LOGIN_URL}?next={request.path}')
        if request.user.role != 'member':
            return redirect(settings.LOGIN_URL)
        return view_func(request, *args, **kwargs)
    return wrapper


def _get_member(request):
    return MemberProfile.objects.select_related('user').get(user=request.user)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _workout_volume_chart(member, weeks=12):
    """Return (labels, counts) for workouts logged per week over last N weeks."""
    from apps.members.models import WorkoutLog

    today = timezone.localdate()
    week_start = today - datetime.timedelta(days=today.weekday())
    start_date = week_start - datetime.timedelta(weeks=weeks - 1)

    log_dates = list(
        WorkoutLog.objects.filter(
            member=member,
            workout_date__gte=start_date,
        ).values_list('workout_date', flat=True)
    )

    labels, counts = [], []
    for i in range(weeks):
        ws = start_date + datetime.timedelta(weeks=i)
        we = ws + datetime.timedelta(days=6)
        labels.append(ws.strftime('%b %d'))
        counts.append(sum(1 for d in log_dates if ws <= d <= we))

    return labels, counts


def _checkin_freq_chart(member, weeks=12):
    """Return (labels, counts) for gym check-ins per week over last N weeks."""
    from apps.checkin.models import CheckIn

    today = timezone.localdate()
    week_start = today - datetime.timedelta(days=today.weekday())
    start_date = week_start - datetime.timedelta(weeks=weeks - 1)

    checkin_dates = list(
        CheckIn.objects.filter(
            member=member,
            checked_in_at__date__gte=start_date,
        ).values_list('checked_in_at', flat=True)
    )
    checkin_dates = [ci.date() if hasattr(ci, 'date') else ci for ci in checkin_dates]

    labels, counts = [], []
    for i in range(weeks):
        ws = start_date + datetime.timedelta(weeks=i)
        we = ws + datetime.timedelta(days=6)
        labels.append(ws.strftime('%b %d'))
        counts.append(sum(1 for d in checkin_dates if ws <= d <= we))

    return labels, counts


def _body_metric_chart(metrics):
    """
    Return Chart.js-ready dicts from BodyMetric queryset (ordered oldest→newest).
    """
    ordered = sorted(metrics, key=lambda m: m.recorded_at)
    return {
        'labels': [m.recorded_at.strftime('%d %b') for m in ordered],
        'weight': [m.weight_kg for m in ordered],
        'body_fat': [m.body_fat_percent for m in ordered],
    }


def _longest_streak(member):
    """Longest consecutive check-in day streak in member's history."""
    from apps.checkin.models import CheckIn

    ci_dates = CheckIn.objects.filter(member=member).values_list('checked_in_at', flat=True)
    if not ci_dates:
        return 0

    dates = sorted({ci.date() for ci in ci_dates})
    if not dates:
        return 0

    longest = current = 1
    for i in range(1, len(dates)):
        if (dates[i] - dates[i - 1]).days == 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest


def _top_prs(member, limit=5):
    """Return top N PR records by max weight lifted, reusing views logic."""
    from apps.members.views import _compute_personal_records
    records = _compute_personal_records(member)
    # Sort by max weight descending, take top N
    return sorted(records, key=lambda r: r['max_weight_kg'], reverse=True)[:limit]


# ---------------------------------------------------------------------------
# Progress home
# ---------------------------------------------------------------------------

@_member_required
def progress_home(request):
    """Main progress dashboard."""
    member = _get_member(request)
    health = getattr(member, 'healthprofile', None)

    # Body metrics (last 30 records, ordered oldest→newest for chart)
    metrics = list(
        BodyMetric.objects.filter(member=member).order_by('-recorded_at')[:30]
    )
    metrics_for_table = metrics[:8]  # Most recent 8 for measurements table

    # Chart data dicts → serialised to JSON for Chart.js
    body_chart = _body_metric_chart(metrics)
    workout_labels, workout_counts = _workout_volume_chart(member)
    checkin_labels, checkin_counts = _checkin_freq_chart(member)

    # Streaks
    from apps.ai_coach.context import calculate_streak
    current_streak = calculate_streak(member)
    longest = _longest_streak(member)

    # Loyalty & badges
    from apps.loyalty.models import MemberBadge
    badge_count = MemberBadge.objects.filter(member=member).count()
    badges = MemberBadge.objects.filter(member=member).select_related('milestone').order_by('-earned_at')[:6]
    total_points = member.loyalty_points

    # PRs
    top_prs = _top_prs(member)

    # Measurements columns for table
    # Pre-process measurements for template (avoids variable dict-key lookups)
    measurement_cols = [
        ('chest_cm', 'Chest'),
        ('waist_cm', 'Waist'),
        ('hips_cm', 'Hips'),
        ('thigh_cm', 'Thigh'),
        ('arm_cm', 'Arm'),
    ]
    # Each row: (metric, [value_or_None, ...]) matching measurement_cols order
    metrics_table_rows = [
        (m, [m.measurements.get(key) for key, _ in measurement_cols])
        for m in metrics_for_table
    ]

    return render(request, 'member/progress.html', {
        'member': member,
        'health': health,
        # Chart JSON (safe to inject into <script>)
        'body_chart_json': json.dumps(body_chart),
        'workout_chart_json': json.dumps({
            'labels': workout_labels,
            'counts': workout_counts,
        }),
        'checkin_chart_json': json.dumps({
            'labels': checkin_labels,
            'counts': checkin_counts,
        }),
        # Stats
        'current_streak': current_streak,
        'longest_streak': longest,
        'total_points': total_points,
        'badge_count': badge_count,
        'badges': badges,
        # PRs
        'top_prs': top_prs,
        # Body metrics table
        'measurement_cols': measurement_cols,
        'metrics_table_rows': metrics_table_rows,
        # Latest metric for display
        'latest_metric': metrics[0] if metrics else None,
    })


# ---------------------------------------------------------------------------
# Log body metric
# ---------------------------------------------------------------------------

@_member_required
@require_POST
def log_body_metric(request):
    """Save a new BodyMetric. Redirects back to progress page."""
    member = _get_member(request)

    recorded_at = request.POST.get('recorded_at') or timezone.localdate()
    weight_raw = request.POST.get('weight_kg', '').strip()
    bf_raw = request.POST.get('body_fat_percent', '').strip()

    weight = float(weight_raw) if weight_raw else None
    body_fat = float(bf_raw) if bf_raw else None

    measurements = {}
    for key in ('chest_cm', 'waist_cm', 'hips_cm', 'thigh_cm', 'arm_cm'):
        val = request.POST.get(key, '').strip()
        if val:
            try:
                measurements[key] = float(val)
            except ValueError:
                pass

    BodyMetric.objects.create(
        member=member,
        recorded_at=recorded_at,
        weight_kg=weight,
        body_fat_percent=body_fat,
        measurements=measurements,
    )

    return redirect('members:progress')

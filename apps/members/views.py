"""
Member registration, onboarding, home screen, and workout tracking views.

Flow:
  /app/register/             Step 1 — Personal info (public, no login required)
  /app/register/waiver/      Step 2 — Accept gym waiver
  /app/register/plans/       Step 3 — Choose membership tier
  /app/register/intake/      Step 4 — AI health intake conversation
  /app/register/intake/send/ HTMX   — Send intake message
  /app/register/intake/complete/    — Finish intake, save HealthProfile
  /app/register/welcome/     Step 5 — Welcome screen
  /app/unavailable/                 — Member app not yet live
"""
import datetime as _dt
from functools import wraps

from django.conf import settings
from django.contrib.auth import login
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.billing.models import MemberMembership, MembershipTier
from apps.core.models import GymProfile
from apps.members.models import HealthProfile, MemberProfile


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


# ---------------------------------------------------------------------------
# AI Intake helpers
# ---------------------------------------------------------------------------

_INTAKE_SYSTEM = """\
You are a friendly health and fitness intake assistant for {gym_name}. \
Your job is to guide a new member through a brief conversational health intake \
to personalise their gym experience.

Cover these topics naturally — one or two at a time, never list them all at once:
1. Primary fitness goal (weight loss, muscle building, endurance, general health, flexibility, sport-specific)
2. Current activity level (sedentary / lightly active / moderately active / very active)
3. Any injuries or physical limitations the gym should know about
4. Dietary preferences or restrictions (vegetarian, vegan, gluten-free, none, etc.)
5. Typical sleep hours per night
6. Stress level (1-10)
7. Preferred workout time (morning / afternoon / evening)

After covering all topics (roughly 6-9 exchanges), end with a warm, encouraging \
summary of what you have learned and say you are ready to personalise their programme.

Rules:
- Be warm, supportive, and concise (2-3 sentences per reply maximum).
- Never provide medical advice.
- Do not mention GymForge anywhere — you represent {gym_name} only.\
"""

# Show "Finish Intake" button after this many assistant turns
_INTAKE_DONE_TURNS = 6


def _get_profile():
    try:
        return GymProfile.objects.get()
    except GymProfile.DoesNotExist:
        return None


def _gym_name(profile):
    return profile.gym_name if profile else 'your gym'


def _start_intake(member_profile, gym_name):
    """Create or retrieve the intake MemberAIConversation, sending the opening message."""
    from apps.ai_coach.client import GymForgeAIClient
    from apps.ai_coach.models import MemberAIConversation

    conv, created = MemberAIConversation.objects.get_or_create(
        member=member_profile,
        session_type='intake',
        defaults={'conversation_history': [], 'started_at': timezone.now()},
    )
    if created:
        system = _INTAKE_SYSTEM.format(gym_name=gym_name)
        client = GymForgeAIClient(system_prompt=system, conversation_history=[])
        client.send_message("Hi! I just joined and I am ready to start my health intake.")
        conv.conversation_history = client.get_history()
        conv.last_message_at = timezone.now()
        conv.save()
    return conv


def _save_intake(member_profile, history):
    hp, _ = HealthProfile.objects.get_or_create(member=member_profile)
    hp.raw_intake_data = history
    hp.intake_completed = True
    hp.last_updated = timezone.now()
    hp.save(update_fields=['raw_intake_data', 'intake_completed', 'last_updated'])


# ---------------------------------------------------------------------------
# Step 1 — Registration form (public)
# ---------------------------------------------------------------------------

def register(request):
    """Create User (role='member') + MemberProfile, log in, redirect to waiver."""
    if request.user.is_authenticated and request.user.role == 'member':
        return redirect('members:register_waiver')

    errors = {}
    data = request.POST if request.method == 'POST' else {}

    if request.method == 'POST':
        first_name = data.get('first_name', '').strip()
        last_name  = data.get('last_name', '').strip()
        email      = data.get('email', '').strip().lower()
        password   = data.get('password', '')
        confirm    = data.get('confirm_password', '')
        dob        = data.get('date_of_birth', '').strip()
        phone      = data.get('phone', '').strip()
        ec_name    = data.get('emergency_contact_name', '').strip()
        ec_phone   = data.get('emergency_contact_phone', '').strip()

        if not first_name:
            errors['first_name'] = 'First name is required.'
        if not last_name:
            errors['last_name'] = 'Last name is required.'
        if not email:
            errors['email'] = 'Email address is required.'
        elif User.objects.filter(email=email).exists():
            errors['email'] = 'An account with this email already exists.'
        if not password or len(password) < 8:
            errors['password'] = 'Password must be at least 8 characters.'
        elif password != confirm:
            errors['confirm_password'] = 'Passwords do not match.'
        if not dob:
            errors['date_of_birth'] = 'Date of birth is required.'

        if not errors:
            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=first_name,
                last_name=last_name,
                password=password,
                role='member',
                phone=phone,
            )
            MemberProfile.objects.create(
                user=user,
                date_of_birth=dob or None,
                emergency_contact_name=ec_name,
                emergency_contact_phone=ec_phone,
            )
            login(request, user)
            return redirect('members:register_waiver')

    return render(request, 'member/register.html', {
        'errors': errors,
        'data': data,
        'profile': _get_profile(),
    })


# ---------------------------------------------------------------------------
# Step 2 — Waiver
# ---------------------------------------------------------------------------

@_member_required
def register_waiver(request):
    try:
        member_profile = request.user.memberprofile
    except MemberProfile.DoesNotExist:
        return redirect('members:register')

    if member_profile.waiver_signed:
        return redirect('members:register_plans')

    profile = _get_profile()
    errors = {}

    if request.method == 'POST':
        if not request.POST.get('accept_waiver'):
            errors['accept_waiver'] = 'You must accept the waiver to continue.'
        else:
            member_profile.waiver_signed = True
            member_profile.waiver_signed_at = timezone.now()
            member_profile.save(update_fields=['waiver_signed', 'waiver_signed_at'])
            return redirect('members:register_plans')

    return render(request, 'member/register_waiver.html', {
        'profile': profile,
        'errors': errors,
    })


# ---------------------------------------------------------------------------
# Step 3 — Membership selection
# ---------------------------------------------------------------------------

@_member_required
def register_plans(request):
    try:
        member_profile = request.user.memberprofile
    except MemberProfile.DoesNotExist:
        return redirect('members:register')

    if not member_profile.waiver_signed:
        return redirect('members:register_waiver')

    tiers = MembershipTier.objects.filter(is_active=True).prefetch_related('included_services')
    errors = {}

    if request.method == 'POST':
        tier_id = request.POST.get('tier_id')
        try:
            tier = MembershipTier.objects.get(pk=tier_id, is_active=True)
        except (MembershipTier.DoesNotExist, ValueError, TypeError):
            errors['tier'] = 'Please select a valid membership plan.'
        else:
            MemberMembership.objects.update_or_create(
                member=member_profile,
                defaults={
                    'tier': tier,
                    'status': 'active',
                    'start_date': timezone.now().date(),
                    'end_date': None,
                },
            )
            return redirect('members:register_intake')

    return render(request, 'member/register_plans.html', {
        'tiers': tiers,
        'errors': errors,
        'profile': _get_profile(),
    })


# ---------------------------------------------------------------------------
# Step 4 — AI health intake
# ---------------------------------------------------------------------------

@_member_required
def register_intake(request):
    try:
        member_profile = request.user.memberprofile
    except MemberProfile.DoesNotExist:
        return redirect('members:register')

    if member_profile.has_completed_intake:
        return redirect('members:register_welcome')

    profile = _get_profile()
    conv = _start_intake(member_profile, _gym_name(profile))
    assistant_turns = sum(1 for m in conv.conversation_history if m.get('role') == 'assistant')

    return render(request, 'member/register_intake.html', {
        'profile': profile,
        'conversation': conv.conversation_history,
        'show_finish': assistant_turns >= _INTAKE_DONE_TURNS,
    })


@require_POST
@_member_required
def register_intake_send(request):
    """HTMX: append one user/AI exchange, return the exchange partial."""
    from apps.ai_coach.client import GymForgeAIClient

    try:
        member_profile = request.user.memberprofile
    except MemberProfile.DoesNotExist:
        return HttpResponse(status=400)

    message = request.POST.get('message', '').strip()
    if not message:
        return HttpResponse(status=400)

    profile = _get_profile()
    gym_name = _gym_name(profile)
    conv = _start_intake(member_profile, gym_name)

    system = _INTAKE_SYSTEM.format(gym_name=gym_name)
    client = GymForgeAIClient(system_prompt=system, conversation_history=conv.conversation_history)
    client.send_message(message)

    conv.conversation_history = client.get_history()
    conv.last_message_at = timezone.now()
    conv.save(update_fields=['conversation_history', 'last_message_at'])

    assistant_turns = sum(1 for m in conv.conversation_history if m.get('role') == 'assistant')

    return render(request, 'member/partials/intake_exchange.html', {
        'user_message': message,
        'reply': client.get_last_reply(),
        'show_finish': assistant_turns >= _INTAKE_DONE_TURNS,
    })


@require_POST
@_member_required
def register_intake_complete(request):
    """Mark intake done, persist HealthProfile, redirect to welcome."""
    from apps.ai_coach.models import MemberAIConversation

    try:
        member_profile = request.user.memberprofile
    except MemberProfile.DoesNotExist:
        return redirect('members:register')

    try:
        conv = MemberAIConversation.objects.get(member=member_profile, session_type='intake')
        _save_intake(member_profile, conv.conversation_history)
    except MemberAIConversation.DoesNotExist:
        hp, _ = HealthProfile.objects.get_or_create(member=member_profile)
        hp.intake_completed = True
        hp.save(update_fields=['intake_completed'])

    return redirect('members:register_welcome')


# ---------------------------------------------------------------------------
# Step 5 — Welcome
# ---------------------------------------------------------------------------

@_member_required
def register_welcome(request):
    try:
        member_profile = request.user.memberprofile
    except MemberProfile.DoesNotExist:
        return redirect('members:register')

    profile = _get_profile()
    app_active = getattr(getattr(request, 'tenant', None), 'member_app_active', False)

    return render(request, 'member/register_welcome.html', {
        'profile': profile,
        'member_profile': member_profile,
        'app_active': app_active,
    })


# ---------------------------------------------------------------------------
# App unavailable
# ---------------------------------------------------------------------------

def app_unavailable(request):
    """Shown when GymTenant.member_app_active is False."""
    return render(request, 'member/unavailable.html', {'profile': _get_profile()})


# ---------------------------------------------------------------------------
# Home screen
# ---------------------------------------------------------------------------

@_member_required
def home(request):
    """Member app home screen — all sections."""
    try:
        member_profile = request.user.memberprofile
    except MemberProfile.DoesNotExist:
        return redirect('members:register')

    app_active = getattr(getattr(request, 'tenant', None), 'member_app_active', False)
    if not app_active:
        return redirect('members:app_unavailable')

    membership = member_profile.active_membership

    # Suspended / overdue / cancelled members see a specific screen
    if membership and membership.status in ('suspended', 'overdue', 'cancelled'):
        return render(request, 'member/membership_suspended.html', {
            'profile': _get_profile(),
            'membership': membership,
        })

    profile = _get_profile()
    today = timezone.now().date()

    # 1. AI daily greeting (session-cached once per calendar day)
    greeting = _get_daily_greeting(request, member_profile, profile)

    # 2. Active workout plan or a goal-based suggestion
    from apps.scheduling.models import WorkoutPlan
    workout_plan = WorkoutPlan.objects.filter(
        member=member_profile, status='active'
    ).first()
    workout_suggestion = None
    if not workout_plan:
        health = getattr(member_profile, 'healthprofile', None)
        if health and health.fitness_goal:
            workout_suggestion = _workout_suggestion(health.fitness_goal)

    # 3. Today's classes at the member's primary location
    from apps.scheduling.models import ClassSession, Booking
    today_sessions = []
    if member_profile.primary_location_id:
        sessions_qs = (
            ClassSession.objects
            .filter(
                location_id=member_profile.primary_location_id,
                start_datetime__date=today,
                is_cancelled=False,
            )
            .select_related('class_type', 'trainer')
            .order_by('start_datetime')
        )
        booked_ids = set(
            Booking.objects.filter(
                member=member_profile,
                class_session__in=sessions_qs,
                status__in=['confirmed', 'waitlisted'],
            ).values_list('class_session_id', flat=True)
        )
        for s in sessions_qs:
            today_sessions.append({
                'session': s,
                'is_booked': s.pk in booked_ids,
                'spots': s.spots_remaining,
            })

    # 4. Stats strip
    from apps.ai_coach.context import calculate_streak
    from apps.checkin.models import CheckIn
    streak_days = calculate_streak(member_profile)
    checkins_this_month = CheckIn.objects.filter(
        member=member_profile,
        checked_in_at__year=today.year,
        checked_in_at__month=today.month,
    ).count()

    # 5. Recent activity feed — last 5 check-ins + last 3 workout logs
    from apps.members.models import WorkoutLog
    recent_checkins = list(
        CheckIn.objects
        .filter(member=member_profile)
        .select_related('location')
        .order_by('-checked_in_at')[:5]
    )
    recent_workouts = list(
        WorkoutLog.objects
        .filter(member=member_profile)
        .order_by('-workout_date')[:3]
    )

    activity_feed = []
    for ci in recent_checkins:
        activity_feed.append({
            'type': 'checkin',
            'sort_dt': ci.checked_in_at,
            'label': f'Checked in — {ci.location.name if ci.location else "gym"}',
            'detail': ci.checked_in_at.strftime('%I:%M %p'),
            'icon': '📍',
        })
    for wl in recent_workouts:
        sort_dt = timezone.make_aware(
            _dt.datetime.combine(wl.workout_date, _dt.time.min)
        )
        activity_feed.append({
            'type': 'workout',
            'sort_dt': sort_dt,
            'label': f'Logged workout — {wl.exercise_count} exercise{"s" if wl.exercise_count != 1 else ""}',
            'detail': f'{wl.duration_minutes or "?"} min',
            'icon': '💪',
        })
    activity_feed.sort(key=lambda x: x['sort_dt'], reverse=True)

    return render(request, 'member/home.html', {
        'profile': profile,
        'member_profile': member_profile,
        'membership': membership,
        'greeting': greeting,
        'workout_plan': workout_plan,
        'workout_suggestion': workout_suggestion,
        'today_sessions': today_sessions,
        'streak_days': streak_days,
        'loyalty_points': member_profile.loyalty_points,
        'checkins_this_month': checkins_this_month,
        'activity_feed': activity_feed,
    })


# ---------------------------------------------------------------------------
# Home helpers
# ---------------------------------------------------------------------------

def _get_daily_greeting(request, member_profile, profile):
    """AI greeting cached in session for the current calendar day."""
    today_str = str(timezone.now().date())
    if (request.session.get('greeting_date') == today_str
            and request.session.get('greeting')):
        return request.session['greeting']

    try:
        from apps.ai_coach.client import GymForgeAIClient
        from apps.ai_coach.context import build_member_context
        from apps.ai_coach.prompts import render_member_prompt

        ctx = build_member_context(member_profile)
        system = render_member_prompt(ctx)
        client = GymForgeAIClient(system_prompt=system, conversation_history=[])
        greeting = client.send_message(
            'Write a short personalized daily greeting for me (2-3 sentences max). '
            'Reference my recent workout activity, current streak, or fitness goal. '
            'Be warm, specific, and motivating. Do not begin with "Hello" or "Hi".'
        )
        request.session['greeting'] = greeting
        request.session['greeting_date'] = today_str
        return greeting
    except Exception:
        name = member_profile.user.first_name or 'there'
        return (
            f"Great to see you today, {name}! "
            "Every session brings you one step closer to your goals."
        )


_WORKOUT_SUGGESTIONS = {
    'weight_loss': {
        'title': 'Fat-Burn Circuit',
        'exercises': [
            {'name': 'Jumping Jacks', 'sets': 3, 'reps': '45 sec'},
            {'name': 'Bodyweight Squats', 'sets': 3, 'reps': '15'},
            {'name': 'Push-Ups', 'sets': 3, 'reps': '12'},
            {'name': 'Mountain Climbers', 'sets': 3, 'reps': '30 sec'},
            {'name': 'Burpees', 'sets': 3, 'reps': '10'},
        ],
    },
    'muscle_building': {
        'title': 'Strength Builder',
        'exercises': [
            {'name': 'Bench Press', 'sets': 4, 'reps': '8-10'},
            {'name': 'Barbell Row', 'sets': 4, 'reps': '8-10'},
            {'name': 'Overhead Press', 'sets': 3, 'reps': '10'},
            {'name': 'Barbell Squat', 'sets': 4, 'reps': '8'},
            {'name': 'Dumbbell Curl', 'sets': 3, 'reps': '12'},
        ],
    },
    'endurance': {
        'title': 'Cardio Endurance',
        'exercises': [
            {'name': 'Treadmill Run', 'sets': 1, 'reps': '20 min'},
            {'name': 'Rowing Machine', 'sets': 3, 'reps': '5 min'},
            {'name': 'Box Step-Ups', 'sets': 3, 'reps': '15 each leg'},
            {'name': 'Jump Rope', 'sets': 4, 'reps': '2 min'},
        ],
    },
    'flexibility': {
        'title': 'Mobility & Flexibility',
        'exercises': [
            {'name': 'Hip Flexor Stretch', 'sets': 2, 'reps': '60 sec each'},
            {'name': 'Downward Dog', 'sets': 3, 'reps': '30 sec'},
            {'name': "World's Greatest Stretch", 'sets': 2, 'reps': '5 each side'},
            {'name': 'Thoracic Rotations', 'sets': 2, 'reps': '10 each side'},
            {'name': 'Cat-Cow', 'sets': 3, 'reps': '10'},
        ],
    },
}
_WORKOUT_SUGGESTIONS['general_health'] = {
    'title': 'Full-Body Wellness',
    'exercises': [
        {'name': 'Goblet Squat', 'sets': 3, 'reps': '12'},
        {'name': 'Dumbbell Row', 'sets': 3, 'reps': '12'},
        {'name': 'Plank Hold', 'sets': 3, 'reps': '30 sec'},
        {'name': 'Lunges', 'sets': 3, 'reps': '10 each leg'},
        {'name': 'Face Pull', 'sets': 3, 'reps': '15'},
    ],
}


def _workout_suggestion(fitness_goal):
    return _WORKOUT_SUGGESTIONS.get(fitness_goal, _WORKOUT_SUGGESTIONS['general_health'])


# ===========================================================================
# Workout tracking — /app/workouts/
# ===========================================================================

import calendar as _calendar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_exercises(post):
    """
    Parse indexed exercise fields from POST into WorkoutLog.exercises JSON format.

    Expected field names:
      exercise_<idx>_name
      exercise_<idx>_set_<set_idx>_reps
      exercise_<idx>_set_<set_idx>_weight_kg
    """
    exercises = []
    idx = 0
    while f'exercise_{idx}_name' in post:
        name = post.get(f'exercise_{idx}_name', '').strip()
        if name:
            sets = []
            set_idx = 0
            while f'exercise_{idx}_set_{set_idx}_reps' in post:
                reps_raw   = post.get(f'exercise_{idx}_set_{set_idx}_reps', '').strip()
                weight_raw = post.get(f'exercise_{idx}_set_{set_idx}_weight_kg', '').strip()
                try:
                    reps = int(reps_raw) if reps_raw else 0
                except ValueError:
                    reps = 0
                try:
                    weight_kg = float(weight_raw) if weight_raw else 0.0
                except ValueError:
                    weight_kg = 0.0
                sets.append({'reps': reps, 'weight_kg': weight_kg})
                set_idx += 1
            if sets:
                exercises.append({'name': name, 'sets': sets})
        idx += 1
    return exercises


def _compute_personal_records(member_profile):
    """
    Return a list of personal-record dicts computed from all WorkoutLog entries.

    Each dict: {name, max_weight_kg, max_weight_reps, max_weight_date,
                        max_reps, max_reps_weight_kg, max_reps_date}
    """
    from apps.members.models import WorkoutLog
    records = {}

    for log in WorkoutLog.objects.filter(member=member_profile):
        for ex in log.exercises:
            name = ex.get('name', '').strip()
            if not name:
                continue
            for s in ex.get('sets', []):
                reps   = s.get('reps', 0) or 0
                weight = s.get('weight_kg', 0.0) or 0.0

                if name not in records:
                    records[name] = {
                        'max_weight_kg':    weight,
                        'max_weight_reps':  reps,
                        'max_weight_date':  log.workout_date,
                        'max_reps':         reps,
                        'max_reps_weight':  weight,
                        'max_reps_date':    log.workout_date,
                    }
                else:
                    r = records[name]
                    if weight > r['max_weight_kg']:
                        r['max_weight_kg']   = weight
                        r['max_weight_reps'] = reps
                        r['max_weight_date'] = log.workout_date
                    if reps > r['max_reps']:
                        r['max_reps']        = reps
                        r['max_reps_weight'] = weight
                        r['max_reps_date']   = log.workout_date

    return [
        {'name': name, **data}
        for name, data in sorted(records.items(), key=lambda x: x[0].lower())
    ]


def _plan_day_exercises(workout_plan):
    """
    Return (focus, exercises) for today's day in the active WorkoutPlan,
    or (None, []) if today is not in the plan.
    """
    day_name = timezone.now().strftime('%A')  # Monday, Tuesday, …
    for week in workout_plan.plan_data.get('weeks', []):
        for day in week.get('days', []):
            if day.get('day', '').lower() == day_name.lower():
                return day.get('focus', ''), day.get('exercises', [])
    return None, []


# ---------------------------------------------------------------------------
# Workout history / main listing
# ---------------------------------------------------------------------------

@_member_required
def workout_history(request):
    from apps.members.models import WorkoutLog
    from apps.ai_coach.context import calculate_streak
    from apps.scheduling.models import WorkoutPlan

    member_profile = _get_member_profile(request)
    if not member_profile:
        return redirect('members:register')

    today   = timezone.now().date()
    year    = int(request.GET.get('year',  today.year))
    month   = int(request.GET.get('month', today.month))

    # Clamp to valid range
    year  = max(2020, min(year,  today.year + 1))
    month = max(1,    min(month, 12))

    # Workout dates this month for calendar highlighting
    workout_dates = set(
        WorkoutLog.objects.filter(
            member=member_profile,
            workout_date__year=year,
            workout_date__month=month,
        ).values_list('workout_date', flat=True)
    )

    # Build calendar grid — list of weeks, each week a list of day-dicts
    raw_cal = _calendar.monthcalendar(year, month)
    cal_weeks = []
    for week in raw_cal:
        week_days = []
        for day_num in week:
            if day_num == 0:
                week_days.append({'day': None, 'has_workout': False, 'is_today': False})
            else:
                d = _dt.date(year, month, day_num)
                week_days.append({
                    'day':         d,
                    'has_workout': d in workout_dates,
                    'is_today':    d == today,
                })
        cal_weeks.append(week_days)

    # Month nav
    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year  = year if month < 12 else year + 1

    # Recent logs (all time, latest first)
    recent_logs = (
        WorkoutLog.objects.filter(member=member_profile)
        .order_by('-workout_date', '-logged_at')[:20]
    )

    # Active plan
    workout_plan = WorkoutPlan.objects.filter(
        member=member_profile, status='active'
    ).first()
    plan_focus, plan_exercises = (None, [])
    if workout_plan:
        plan_focus, plan_exercises = _plan_day_exercises(workout_plan)

    streak_days = calculate_streak(member_profile)

    return render(request, 'member/workout_history.html', {
        'profile':          _get_profile(),
        'cal_weeks':        cal_weeks,
        'month_name':       _dt.date(year, month, 1).strftime('%B %Y'),
        'prev_year':        prev_year,
        'prev_month':       prev_month,
        'next_year':        next_year,
        'next_month':       next_month,
        'recent_logs':      recent_logs,
        'streak_days':      streak_days,
        'workout_plan':     workout_plan,
        'plan_focus':       plan_focus,
        'plan_exercises':   plan_exercises,
        'today':            today,
    })


# ---------------------------------------------------------------------------
# Log workout form
# ---------------------------------------------------------------------------

@_member_required
def workout_log(request):
    from apps.members.models import WorkoutLog
    from apps.scheduling.models import WorkoutPlan

    member_profile = _get_member_profile(request)
    if not member_profile:
        return redirect('members:register')

    errors = {}

    if request.method == 'POST':
        date_str  = request.POST.get('workout_date', '').strip()
        dur_str   = request.POST.get('duration_minutes', '').strip()
        mood_str  = request.POST.get('mood_before', '').strip()
        energy_str = request.POST.get('energy_after', '').strip()
        notes     = request.POST.get('notes', '').strip()

        if not date_str:
            errors['workout_date'] = 'Date is required.'

        exercises = _parse_exercises(request.POST)
        if not exercises:
            errors['exercises'] = 'Add at least one exercise.'

        if not errors:
            WorkoutLog.objects.create(
                member=member_profile,
                workout_date=date_str,
                source='manual',
                duration_minutes=int(dur_str) if dur_str.isdigit() else None,
                exercises=exercises,
                mood_before=int(mood_str)   if mood_str.isdigit()   else None,
                energy_after=int(energy_str) if energy_str.isdigit() else None,
                notes=notes,
            )
            return redirect('members:workout_history')

    # Pre-fill from active workout plan for today?
    prefill_exercises = []
    plan_focus = None
    workout_plan = WorkoutPlan.objects.filter(
        member=member_profile, status='active'
    ).first()
    if workout_plan:
        plan_focus, plan_exs = _plan_day_exercises(workout_plan)
        for ex in plan_exs:
            sets_count = ex.get('sets', 3)
            try:
                sets_count = int(sets_count)
            except (TypeError, ValueError):
                sets_count = 3
            prefill_exercises.append({
                'name':      ex.get('name', ''),
                'set_range': list(range(sets_count)),
                'reps_hint': str(ex.get('reps', '')),
            })

    today = timezone.now().date().isoformat()

    return render(request, 'member/workout_log.html', {
        'profile':            _get_profile(),
        'errors':             errors,
        'today':              today,
        'prefill_exercises':  prefill_exercises,
        'plan_focus':         plan_focus,
        'post':               request.POST,
    })


# ---------------------------------------------------------------------------
# Personal records
# ---------------------------------------------------------------------------

@_member_required
def personal_records(request):
    member_profile = _get_member_profile(request)
    if not member_profile:
        return redirect('members:register')

    records = _compute_personal_records(member_profile)

    return render(request, 'member/personal_records.html', {
        'profile': _get_profile(),
        'records': records,
    })


# ---------------------------------------------------------------------------
# HTMX partial — add exercise row
# ---------------------------------------------------------------------------

@_member_required
def exercise_row_partial(request):
    """Return an empty exercise row partial for HTMX append."""
    idx       = int(request.GET.get('idx', 0))
    set_count = max(1, int(request.GET.get('sets', 3)))
    return render(request, 'member/partials/exercise_row.html', {
        'idx':         idx,
        'set_indices': list(range(set_count)),
        'name':        '',
        'reps_hint':   '',
    })

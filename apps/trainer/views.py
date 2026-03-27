import json
import re
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.ai_coach.client import GymForgeAIClient
from apps.ai_coach.context import build_member_context
from apps.checkin.models import ClientAssignment
from apps.members.models import MemberProfile
from apps.scheduling.models import Appointment, WorkoutPlan


_TRAINER_ROLES = {'trainer', 'head_trainer', 'gym_owner', 'platform_admin'}

_PLAN_PROMPT = """You are an expert personal trainer. Generate a structured 4-week workout plan for this client.

Return ONLY valid JSON in this exact format (no markdown, no extra text):
{
  "weeks": [
    {
      "week": 1,
      "days": [
        {
          "day": "Monday",
          "focus": "Upper Body Push",
          "exercises": [
            {"name": "Bench Press", "sets": 3, "reps": "8-10", "rest_sec": 90},
            {"name": "Overhead Press", "sets": 3, "reps": "8-10", "rest_sec": 90}
          ]
        }
      ]
    }
  ]
}

Include 3-4 training days per week. Rest days should not appear in the JSON. Tailor intensity to the client's goal and fitness level."""


def _trainer_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role not in _TRAINER_ROLES:
            return HttpResponseForbidden("Trainer access required.")
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def _assigned_member_ids(trainer):
    return ClientAssignment.objects.filter(
        staff=trainer, assignment_type='trainer', is_active=True
    ).values_list('member_id', flat=True)


def _get_assigned_member(trainer, member_pk):
    assigned_ids = _assigned_member_ids(trainer)
    return get_object_or_404(MemberProfile, pk=member_pk, id__in=assigned_ids)


def _extract_json(text: str) -> dict:
    text = re.sub(r'```(?:json)?', '', text).strip().replace('```', '').strip()
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in AI response")
    return json.loads(text[start:end + 1])


# ---------------------------------------------------------------------------
# Client list (dashboard)
# ---------------------------------------------------------------------------

@_trainer_required
def client_list(request):
    assigned_ids = _assigned_member_ids(request.user)
    members = MemberProfile.objects.filter(id__in=assigned_ids).select_related('healthprofile')
    today = date.today()
    week_end = today + timedelta(days=6)

    upcoming_appointments = Appointment.objects.filter(
        staff=request.user,
        member_id__in=assigned_ids,
        scheduled_at__date__gte=today,
        scheduled_at__date__lte=week_end,
        status__in=['pending', 'confirmed'],
    ).select_related('member').order_by('scheduled_at')[:5]

    client_data = []
    for m in members:
        last_log = m.workout_logs.order_by('-workout_date').first()
        next_appt = Appointment.objects.filter(
            staff=request.user, member=m,
            scheduled_at__gte=timezone.now(),
            status__in=['pending', 'confirmed'],
        ).order_by('scheduled_at').first()
        active_plan = m.workout_plans.filter(status='active').first()
        hp = getattr(m, 'healthprofile', None)
        client_data.append({
            'member': m,
            'goal': getattr(hp, 'fitness_goal', '—') or '—',
            'last_workout': last_log.workout_date if last_log else None,
            'next_appointment': next_appt,
            'active_plan': active_plan,
        })

    return render(request, 'trainer/client_list.html', {
        'client_data': client_data,
        'upcoming_appointments': upcoming_appointments,
        'today': today,
    })


# ---------------------------------------------------------------------------
# Client detail
# ---------------------------------------------------------------------------

@_trainer_required
def client_detail(request, member_pk):
    member = _get_assigned_member(request.user, member_pk)
    health = getattr(member, 'healthprofile', None)
    recent_logs = member.workout_logs.order_by('-workout_date')[:10]
    recent_metrics = member.body_metrics.order_by('-recorded_at')[:5]
    active_plan = member.workout_plans.filter(status='active').first()
    draft_plans = member.workout_plans.filter(status='draft').order_by('-created_at')
    upcoming_appointments = Appointment.objects.filter(
        staff=request.user, member=member,
        scheduled_at__gte=timezone.now(),
        status__in=['pending', 'confirmed'],
    ).order_by('scheduled_at')[:5]

    return render(request, 'trainer/client_detail.html', {
        'member': member,
        'health': health,
        'recent_logs': recent_logs,
        'recent_metrics': recent_metrics,
        'active_plan': active_plan,
        'draft_plans': draft_plans,
        'upcoming_appointments': upcoming_appointments,
    })


# ---------------------------------------------------------------------------
# Workout plan list
# ---------------------------------------------------------------------------

@_trainer_required
def workout_plan_list(request):
    assigned_ids = _assigned_member_ids(request.user)
    plans = WorkoutPlan.objects.filter(
        member_id__in=assigned_ids
    ).select_related('member').order_by('-created_at')
    return render(request, 'trainer/workout_plan_list.html', {'plans': plans})


# ---------------------------------------------------------------------------
# AI plan generation
# ---------------------------------------------------------------------------

@_trainer_required
def generate_plan(request, member_pk):
    member = _get_assigned_member(request.user, member_pk)

    if request.method == 'POST':
        try:
            ctx = build_member_context(member)
            system_prompt = (
                f"You are a personal trainer at {ctx.get('gym_name', 'the gym')}. "
                f"You are creating a 4-week workout plan for {ctx.get('member_name', 'a client')}.\n"
                f"Goal: {ctx.get('fitness_goal', 'general fitness')}\n"
                f"Activity level: {ctx.get('activity_level', 'moderate')}\n"
                f"Injuries/limitations: {ctx.get('injuries_limitations', 'none')}\n"
                f"Preferred workout time: {ctx.get('preferred_workout_time', 'any')}\n"
                f"Recent workout summary: {ctx.get('workout_summary', 'no history')}"
            )
            ai_client = GymForgeAIClient(
                system_prompt=system_prompt,
                conversation_history=[],
            )
            reply = ai_client.send_message(_PLAN_PROMPT)
            plan_data = _extract_json(reply)

            plan = WorkoutPlan.objects.create(
                member=member,
                created_by=request.user,
                source='ai',
                status='draft',
                plan_data=plan_data,
            )
            messages.success(request, "AI workout plan generated. Review and approve below.")
            return redirect('trainer:plan_review', plan_pk=plan.pk)
        except Exception as e:
            messages.error(request, f"Plan generation failed: {e}")
            return redirect('trainer:client_detail', member_pk=member_pk)

    return render(request, 'trainer/generate_plan.html', {'member': member})


# ---------------------------------------------------------------------------
# Plan review / edit / approve
# ---------------------------------------------------------------------------

@_trainer_required
def plan_review(request, plan_pk):
    assigned_ids = _assigned_member_ids(request.user)
    plan = get_object_or_404(WorkoutPlan, pk=plan_pk, member_id__in=assigned_ids)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'save_edits':
            try:
                plan.plan_data = json.loads(request.POST.get('plan_json', '{}'))
                plan.save(update_fields=['plan_data'])
                messages.success(request, "Plan edits saved.")
            except json.JSONDecodeError:
                messages.error(request, "Invalid JSON — check your edits.")
            return redirect('trainer:plan_review', plan_pk=plan.pk)

        if action == 'approve':
            WorkoutPlan.objects.filter(
                member=plan.member, status='active'
            ).exclude(pk=plan.pk).update(status='archived')
            plan.status = 'active'
            plan.approved_at = timezone.now()
            plan.save(update_fields=['status', 'approved_at'])
            messages.success(request, "Plan approved and set as active.")
            return redirect('trainer:client_detail', member_pk=plan.member_id)

    plan_json = json.dumps(plan.plan_data, indent=2)
    return render(request, 'trainer/plan_review.html', {
        'plan': plan,
        'plan_json': plan_json,
    })


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

@_trainer_required
def schedule(request):
    today = date.today()
    week_offset = int(request.GET.get('week', 0))
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=6)

    assigned_ids = _assigned_member_ids(request.user)
    appointments = Appointment.objects.filter(
        staff=request.user,
        member_id__in=assigned_ids,
        scheduled_at__date__gte=week_start,
        scheduled_at__date__lte=week_end,
    ).select_related('member').order_by('scheduled_at')

    return render(request, 'trainer/schedule.html', {
        'appointments': appointments,
        'week_start': week_start,
        'week_end': week_end,
        'today': today,
        'prev_week': week_offset - 1,
        'next_week': week_offset + 1,
        'week_offset': week_offset,
    })


# ---------------------------------------------------------------------------
# Session logging
# ---------------------------------------------------------------------------

@_trainer_required
def session_log(request, appointment_pk):
    assigned_ids = _assigned_member_ids(request.user)
    appt = get_object_or_404(
        Appointment,
        pk=appointment_pk,
        staff=request.user,
        member_id__in=assigned_ids,
    )

    if request.method == 'POST':
        appt.notes_after = request.POST.get('notes_after', '').strip()
        appt.status = 'completed'
        appt.save(update_fields=['notes_after', 'status'])
        messages.success(request, "Session logged as completed.")
        return redirect('trainer:schedule')

    return render(request, 'trainer/session_log.html', {'appt': appt})

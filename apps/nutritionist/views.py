"""
Nutritionist portal views.

CRITICAL: Every queryset is scoped to members assigned via ClientAssignment
(assignment_type='nutritionist'). Nutritionists cannot see any other members.
"""
import json
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.checkin.models import ClientAssignment
from apps.members.models import MemberProfile, NutritionRecommendation, SupplementRecommendation
from apps.scheduling.models import Appointment


_NUTRITIONIST_ROLES = {'nutritionist', 'manager', 'gym_owner', 'platform_admin'}


def _nutritionist_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role not in _NUTRITIONIST_ROLES:
            return HttpResponseForbidden("Nutritionist access required.")
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def _assigned_member_ids(nutritionist):
    return ClientAssignment.objects.filter(
        staff=nutritionist, assignment_type='nutritionist', is_active=True
    ).values_list('member_id', flat=True)


def _get_assigned_member(nutritionist, member_pk):
    assigned_ids = _assigned_member_ids(nutritionist)
    return get_object_or_404(MemberProfile, pk=member_pk, id__in=assigned_ids)


# ---------------------------------------------------------------------------
# Client list (dashboard)
# ---------------------------------------------------------------------------

@_nutritionist_required
def client_list(request):
    assigned_ids = _assigned_member_ids(request.user)
    members = MemberProfile.objects.filter(id__in=assigned_ids).select_related('healthprofile', 'user')

    today = date.today()
    upcoming_appointments = Appointment.objects.filter(
        staff=request.user,
        member_id__in=assigned_ids,
        appointment_type='nutrition',
        scheduled_at__date__gte=today,
        status__in=['pending', 'confirmed'],
    ).select_related('member').order_by('scheduled_at')[:5]

    client_data = []
    for m in members:
        hp = getattr(m, 'healthprofile', None)
        latest_plan = m.nutrition_recommendations.order_by('-generated_at').first()
        next_appt = Appointment.objects.filter(
            staff=request.user, member=m,
            appointment_type='nutrition',
            scheduled_at__gte=timezone.now(),
            status__in=['pending', 'confirmed'],
        ).order_by('scheduled_at').first()
        client_data.append({
            'member': m,
            'dietary_preference': getattr(hp, 'dietary_preference', '—') or '—',
            'latest_plan': latest_plan,
            'next_appointment': next_appt,
        })

    return render(request, 'nutritionist/client_list.html', {
        'client_data': client_data,
        'upcoming_appointments': upcoming_appointments,
    })


# ---------------------------------------------------------------------------
# Client detail
# ---------------------------------------------------------------------------

@_nutritionist_required
def client_detail(request, member_pk):
    member = _get_assigned_member(request.user, member_pk)
    health = getattr(member, 'healthprofile', None)
    latest_plan = member.nutrition_recommendations.order_by('-generated_at').first()
    supplements = member.supplement_recommendations.order_by('-generated_at')
    upcoming_appointments = Appointment.objects.filter(
        staff=request.user, member=member,
        appointment_type='nutrition',
        scheduled_at__gte=timezone.now(),
        status__in=['pending', 'confirmed'],
    ).order_by('scheduled_at')[:5]
    disclaimer = SupplementRecommendation.SUPPLEMENT_DISCLAIMER

    return render(request, 'nutritionist/client_detail.html', {
        'member': member,
        'health': health,
        'latest_plan': latest_plan,
        'supplements': supplements,
        'upcoming_appointments': upcoming_appointments,
        'disclaimer': disclaimer,
    })


# ---------------------------------------------------------------------------
# Nutrition plan list
# ---------------------------------------------------------------------------

@_nutritionist_required
def plan_list(request):
    assigned_ids = _assigned_member_ids(request.user)
    plans = NutritionRecommendation.objects.filter(
        member_id__in=assigned_ids
    ).select_related('member').order_by('-generated_at')
    return render(request, 'nutritionist/plan_list.html', {'plans': plans})


# ---------------------------------------------------------------------------
# Meal plan builder (create / edit)
# ---------------------------------------------------------------------------

@_nutritionist_required
def plan_form(request, member_pk, plan_pk=None):
    member = _get_assigned_member(request.user, member_pk)
    health = getattr(member, 'healthprofile', None)

    plan = None
    if plan_pk:
        assigned_ids = _assigned_member_ids(request.user)
        plan = get_object_or_404(
            NutritionRecommendation, pk=plan_pk, member_id__in=assigned_ids
        )

    if request.method == 'POST':
        # Macro targets
        def _int(key):
            try:
                return int(request.POST.get(key, '') or 0) or None
            except ValueError:
                return None

        daily_calories = _int('daily_calories')
        protein_g = _int('protein_g')
        carbs_g = _int('carbs_g')
        fat_g = _int('fat_g')
        nutritionist_notes = request.POST.get('nutritionist_notes', '').strip()

        # Meal plan from textareas → list of text items
        meal_plan = {}
        for meal in ('breakfast', 'lunch', 'dinner', 'snacks'):
            raw = request.POST.get(f'meal_{meal}', '').strip()
            if raw:
                items = [line.strip() for line in raw.splitlines() if line.strip()]
                meal_plan[meal] = [{'item': item, 'calories': None, 'protein_g': None} for item in items]

        if plan:
            plan.daily_calories = daily_calories
            plan.protein_g = protein_g
            plan.carbs_g = carbs_g
            plan.fat_g = fat_g
            plan.meal_plan = meal_plan
            plan.nutritionist_notes = nutritionist_notes
            plan.nutritionist_reviewed = True
            plan.save()
            messages.success(request, "Nutrition plan updated.")
        else:
            plan = NutritionRecommendation.objects.create(
                member=member,
                daily_calories=daily_calories,
                protein_g=protein_g,
                carbs_g=carbs_g,
                fat_g=fat_g,
                meal_plan=meal_plan,
                nutritionist_notes=nutritionist_notes,
                nutritionist_reviewed=True,
            )
            messages.success(request, f"Nutrition plan created for {member.full_name}.")

        return redirect('nutritionist:client_detail', member_pk=member_pk)

    # Pre-fill meal textarea values from existing plan
    meal_prefill = {}
    if plan and plan.meal_plan:
        for meal in ('breakfast', 'lunch', 'dinner', 'snacks'):
            items = plan.meal_plan.get(meal, [])
            meal_prefill[meal] = '\n'.join(
                i.get('item', '') if isinstance(i, dict) else str(i)
                for i in items
            )

    return render(request, 'nutritionist/plan_form.html', {
        'member': member,
        'health': health,
        'plan': plan,
        'meal_breakfast': meal_prefill.get('breakfast', ''),
        'meal_lunch': meal_prefill.get('lunch', ''),
        'meal_dinner': meal_prefill.get('dinner', ''),
        'meal_snacks': meal_prefill.get('snacks', ''),
    })


# ---------------------------------------------------------------------------
# Supplement review
# ---------------------------------------------------------------------------

@_nutritionist_required
def supplement_review(request, supplement_pk):
    assigned_ids = _assigned_member_ids(request.user)
    supp = get_object_or_404(
        SupplementRecommendation,
        pk=supplement_pk,
        member_id__in=assigned_ids,
    )
    disclaimer = SupplementRecommendation.SUPPLEMENT_DISCLAIMER

    if request.method == 'POST':
        supp.professional_override = request.POST.get('professional_override', '').strip()
        supp.override_by = request.user
        supp.save(update_fields=['professional_override', 'override_by'])
        messages.success(request, "Professional override saved.")
        return redirect('nutritionist:client_detail', member_pk=supp.member_id)

    return render(request, 'nutritionist/supplement_review.html', {
        'supp': supp,
        'disclaimer': disclaimer,
    })


# ---------------------------------------------------------------------------
# Appointments (schedule view)
# ---------------------------------------------------------------------------

@_nutritionist_required
def appointments(request):
    assigned_ids = _assigned_member_ids(request.user)
    today = date.today()
    upcoming = Appointment.objects.filter(
        staff=request.user,
        member_id__in=assigned_ids,
        appointment_type='nutrition',
        scheduled_at__date__gte=today,
        status__in=['pending', 'confirmed'],
    ).select_related('member').order_by('scheduled_at')

    past = Appointment.objects.filter(
        staff=request.user,
        member_id__in=assigned_ids,
        appointment_type='nutrition',
        scheduled_at__date__lt=today,
    ).select_related('member').order_by('-scheduled_at')[:20]

    return render(request, 'nutritionist/appointments.html', {
        'upcoming': upcoming,
        'past': past,
        'today': today,
    })


# ---------------------------------------------------------------------------
# Log / complete appointment
# ---------------------------------------------------------------------------

@_nutritionist_required
def appointment_log(request, appointment_pk):
    assigned_ids = _assigned_member_ids(request.user)
    appt = get_object_or_404(
        Appointment,
        pk=appointment_pk,
        staff=request.user,
        member_id__in=assigned_ids,
        appointment_type='nutrition',
    )

    if request.method == 'POST':
        appt.notes_after = request.POST.get('notes_after', '').strip()
        appt.status = 'completed'
        appt.save(update_fields=['notes_after', 'status'])
        messages.success(request, "Consultation logged as completed.")
        return redirect('nutritionist:appointments')

    return render(request, 'nutritionist/appointment_log.html', {'appt': appt})

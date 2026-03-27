"""
Nutrition and supplement views for the member portal (/app/nutrition/).

All views require role='member'. Mounted via apps/members/urls.py.

AI meal plan generation and meal-swap both call GymForgeAIClient with the
member's health-profile context so recommendations are personalised.
"""
import json
import re
from functools import wraps

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.members.models import (
    MemberProfile,
    NutritionRecommendation,
    SupplementRecommendation,
)


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
# AI helpers
# ---------------------------------------------------------------------------

_MEAL_PLAN_PROMPT = """
Generate a personalised one-day meal plan for this member. Return ONLY valid
JSON — no explanation, no markdown fences — in exactly this structure:

{
  "breakfast": [{"name": "...", "description": "..."}],
  "lunch":     [{"name": "...", "description": "..."}],
  "dinner":    [{"name": "...", "description": "..."}],
  "snacks":    [{"name": "...", "description": "..."}],
  "daily_calories": <integer>,
  "protein_g":      <integer>,
  "carbs_g":        <integer>,
  "fat_g":          <integer>
}

Rules:
- Respect the member's dietary preference, food allergies, and disliked foods.
- Aim for 3-5 items per meal section.
- Keep descriptions brief (one sentence each).
- Macro totals must be consistent with daily_calories.
""".strip()


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from an AI response string."""
    # Strip markdown code fences if present
    text = re.sub(r'```(?:json)?', '', text).strip()
    # Find the outermost { ... }
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1:
        raise ValueError('No JSON object found in AI response')
    return json.loads(text[start:end + 1])


def _build_ai_client(member_profile):
    """Build a one-shot GymForgeAIClient with this member's context."""
    from apps.ai_coach.client import GymForgeAIClient
    from apps.ai_coach.context import build_member_context
    from apps.ai_coach.prompts import render_member_prompt

    ctx = build_member_context(member_profile)
    system = render_member_prompt(ctx)
    return GymForgeAIClient(system_prompt=system, conversation_history=[])


def _generate_plan(member_profile) -> NutritionRecommendation:
    """
    Call the AI to produce a meal plan and persist it as a
    NutritionRecommendation. Returns the new record.
    On AI/parse failure, creates a minimal placeholder record.
    """
    try:
        client = _build_ai_client(member_profile)
        reply = client.send_message(_MEAL_PLAN_PROMPT)
        data = _extract_json(reply)

        rec = NutritionRecommendation.objects.create(
            member=member_profile,
            daily_calories=data.get('daily_calories'),
            protein_g=data.get('protein_g'),
            carbs_g=data.get('carbs_g'),
            fat_g=data.get('fat_g'),
            meal_plan={
                'breakfast': data.get('breakfast', []),
                'lunch': data.get('lunch', []),
                'dinner': data.get('dinner', []),
                'snacks': data.get('snacks', []),
            },
        )
    except Exception:
        # Fallback: empty plan so the page still renders
        rec = NutritionRecommendation.objects.create(
            member=member_profile,
            meal_plan={'breakfast': [], 'lunch': [], 'dinner': [], 'snacks': []},
        )
    return rec


# ---------------------------------------------------------------------------
# Nutrition home
# ---------------------------------------------------------------------------

@_member_required
def nutrition_home(request):
    """
    Main nutrition page.

    Loads the most recent NutritionRecommendation. If none exists, generates
    one automatically so first-time visitors always see a plan.
    """
    member = _get_member(request)

    plan = NutritionRecommendation.objects.filter(member=member).first()
    if plan is None:
        plan = _generate_plan(member)

    supplements = SupplementRecommendation.objects.filter(member=member)
    disclaimer = SupplementRecommendation.SUPPLEMENT_DISCLAIMER

    meals = [
        ('breakfast', 'Breakfast',  '🌅', plan.meal_plan.get('breakfast', [])),
        ('lunch',     'Lunch',      '☀️',  plan.meal_plan.get('lunch', [])),
        ('dinner',    'Dinner',     '🌙', plan.meal_plan.get('dinner', [])),
        ('snacks',    'Snacks',     '🍎', plan.meal_plan.get('snacks', [])),
    ]

    return render(request, 'member/nutrition.html', {
        'plan': plan,
        'meals': meals,
        'supplements': supplements,
        'disclaimer': disclaimer,
        'member': member,
    })


# ---------------------------------------------------------------------------
# Generate / regenerate plan
# ---------------------------------------------------------------------------

@_member_required
@require_POST
def generate_nutrition_plan(request):
    """
    Generate a fresh NutritionRecommendation and return the updated meal-plan
    section via HTMX (replaces #nutrition-plan-container).
    """
    member = _get_member(request)
    plan = _generate_plan(member)

    meals = [
        ('breakfast', 'Breakfast',  '🌅', plan.meal_plan.get('breakfast', [])),
        ('lunch',     'Lunch',      '☀️',  plan.meal_plan.get('lunch', [])),
        ('dinner',    'Dinner',     '🌙', plan.meal_plan.get('dinner', [])),
        ('snacks',    'Snacks',     '🍎', plan.meal_plan.get('snacks', [])),
    ]

    return render(request, 'member/partials/nutrition_plan.html', {
        'plan': plan,
        'meals': meals,
        'member': member,
    })


# ---------------------------------------------------------------------------
# Swap a meal item
# ---------------------------------------------------------------------------

@_member_required
@require_POST
def swap_meal_item(request, plan_id):
    """
    Replace one meal item with an AI-suggested alternative.

    POST params:
      meal_type  — 'breakfast' | 'lunch' | 'dinner' | 'snacks'
      item_index — 0-based index of the item to replace
      item_name  — display name of the current item (for the AI prompt)

    Returns the updated meal-section partial via HTMX.
    """
    member = _get_member(request)
    try:
        plan = NutritionRecommendation.objects.get(pk=plan_id, member=member)
    except NutritionRecommendation.DoesNotExist:
        return HttpResponse(status=404)

    meal_type = request.POST.get('meal_type', '')
    item_name = request.POST.get('item_name', '')
    try:
        item_index = int(request.POST.get('item_index', 0))
    except ValueError:
        item_index = 0

    valid_types = ('breakfast', 'lunch', 'dinner', 'snacks')
    if meal_type not in valid_types:
        return HttpResponse(status=400)

    swap_prompt = (
        f'Swap this {meal_type} item: "{item_name}". '
        'Return ONLY a JSON object (no markdown, no extra text):\n'
        '{"name": "...", "description": "..."}\n'
        'The replacement must respect this member\'s dietary preferences and allergies.'
    )

    new_item = {'name': item_name, 'description': ''}
    try:
        client = _build_ai_client(member)
        reply = client.send_message(swap_prompt)
        new_item = _extract_json(reply)
    except Exception:
        pass  # Keep original on AI failure

    # Update the meal_plan JSONField in place
    meal_plan = plan.meal_plan.copy()
    items = meal_plan.get(meal_type, [])
    if item_index < len(items):
        items[item_index] = new_item
    meal_plan[meal_type] = items
    plan.meal_plan = meal_plan
    plan.save(update_fields=['meal_plan'])

    # Return the meal-type labels for the partial
    label_map = {
        'breakfast': ('Breakfast', '🌅'),
        'lunch': ('Lunch', '☀️'),
        'dinner': ('Dinner', '🌙'),
        'snacks': ('Snacks', '🍎'),
    }
    label, icon = label_map[meal_type]

    return render(request, 'member/partials/meal_section.html', {
        'meal_type': meal_type,
        'meal_label': label,
        'meal_icon': icon,
        'items': items,
        'plan': plan,
    })

"""
Member AI Coach views — mounted at /app/ai/ via ai_coach.urls.

Endpoints:
  GET  /app/ai/              — chat UI (load or create conversation)
  POST /app/ai/send/         — HTMX: send a message, return ai_message.html partial
  POST /app/ai/new/          — start a fresh conversation
  POST /app/ai/session-type/ — switch session type (creates new conversation)
"""
from functools import wraps

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.members.models import MemberProfile, SupplementRecommendation


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
# Session type registry & suggested prompts
# ---------------------------------------------------------------------------

SESSION_TYPES = [
    ('general',   'General',       '💬'),
    ('workout',   'Workout',       '💪'),
    ('nutrition', 'Nutrition',     '🥗'),
    ('intake',    'Health Intake', '📋'),
]

_SESSION_TYPE_SET = {t[0] for t in SESSION_TYPES}

SUGGESTED_PROMPTS = {
    'general': [
        'Create me a 4-week workout plan',
        'How am I progressing toward my goal?',
        'What should I focus on this week?',
        "I'm feeling unmotivated — help me",
        'How many calories should I eat daily?',
        'Tips for better sleep and recovery',
    ],
    'workout': [
        'Build me a push/pull/legs split',
        'Best exercises for my fitness goal',
        'How do I improve my bench press?',
        'Design a 30-minute home workout',
        'Explain progressive overload to me',
        'How long should I rest between sets?',
    ],
    'nutrition': [
        'What should I eat today?',
        'Give me high-protein meal ideas',
        'What should I eat before a workout?',
        'How much protein do I need daily?',
        'Quick healthy meal prep for the week',
        'Best foods for my fitness goal',
    ],
    'intake': [
        'I want to update my fitness goals',
        'I have a new injury to mention',
        'My diet has changed recently',
        'Update my preferred workout time',
    ],
}

# Keywords that require SUPPLEMENT_DISCLAIMER to be appended
_SUPPLEMENT_KEYWORDS = (
    'supplement', 'protein powder', 'creatine', 'vitamin d', 'vitamin c',
    'omega-3', 'fish oil', 'bcaa', 'pre-workout', 'whey', 'casein',
    'collagen', 'zinc', 'magnesium', 'melatonin', 'probiotic',
    'electrolyte', 'multivitamin',
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_member_profile(request):
    try:
        return request.user.memberprofile
    except MemberProfile.DoesNotExist:
        return None


def _get_or_create_conversation(member_profile, session_type):
    """Return the most recent conversation of this type, or create a new one."""
    from apps.ai_coach.models import MemberAIConversation
    conv = (
        MemberAIConversation.objects
        .filter(member=member_profile, session_type=session_type)
        .order_by('-last_message_at')
        .first()
    )
    if conv is None:
        conv = MemberAIConversation.objects.create(
            member=member_profile,
            session_type=session_type,
            conversation_history=[],
            started_at=timezone.now(),
        )
    return conv


def _build_system_prompt(member_profile, session_type):
    from apps.ai_coach.context import build_member_context
    from apps.ai_coach.prompts import render_member_prompt

    ctx = build_member_context(member_profile)

    # Inject a session-mode hint so the AI stays focused
    mode_hints = {
        'workout': (
            '[SESSION MODE: workout — focus on exercise programming, '
            'technique, sets/reps, and training plans.]\n'
        ),
        'nutrition': (
            '[SESSION MODE: nutrition — focus on diet, macros, '
            'meal planning, and hydration.]\n'
        ),
        'intake': (
            '[SESSION MODE: health intake — guide the member through '
            'updating their health and fitness profile.]\n'
        ),
    }
    hint = mode_hints.get(session_type, '')
    ctx['gym_additional_context'] = hint + ctx.get('gym_additional_context', '')

    return render_member_prompt(ctx)


def _check_and_apply_disclaimer(reply: str):
    """
    Return (display_reply, show_disclaimer, storage_reply).

    display_reply  — clean text shown in the chat bubble
    show_disclaimer — bool, True when the reply touches supplements
    storage_reply   — text saved to conversation history (includes disclaimer)
    """
    lower = reply.lower()
    triggered = any(kw in lower for kw in _SUPPLEMENT_KEYWORDS)

    if not triggered:
        return reply, False, reply

    disclaimer = SupplementRecommendation.SUPPLEMENT_DISCLAIMER
    # Avoid double-appending if AI already included the text
    if disclaimer[:40].lower() in lower:
        return reply, False, reply

    storage_reply = f"{reply}\n\n{disclaimer}"
    return reply, True, storage_reply


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

@_member_required
def chat(request):
    """Main AI Coach chat page."""
    member_profile = _get_member_profile(request)
    if not member_profile:
        return redirect('members:register')

    session_type = request.GET.get('type', request.session.get('ai_session_type', 'general'))
    if session_type not in _SESSION_TYPE_SET:
        session_type = 'general'
    request.session['ai_session_type'] = session_type

    conv = _get_or_create_conversation(member_profile, session_type)

    return render(request, 'member/ai_chat.html', {
        'conversation': conv.conversation_history,
        'conv_id': conv.pk,
        'session_type': session_type,
        'session_types': SESSION_TYPES,
        'suggested_prompts': SUGGESTED_PROMPTS.get(session_type, []),
        'disclaimer': SupplementRecommendation.SUPPLEMENT_DISCLAIMER,
    })


@require_POST
@_member_required
def chat_send(request):
    """HTMX POST: send a user message and return the exchange partial."""
    from apps.ai_coach.client import GymForgeAIClient

    member_profile = _get_member_profile(request)
    if not member_profile:
        return HttpResponse(status=400)

    message = request.POST.get('message', '').strip()
    if not message:
        return HttpResponse(status=400)

    session_type = request.session.get('ai_session_type', 'general')
    conv = _get_or_create_conversation(member_profile, session_type)

    system = _build_system_prompt(member_profile, session_type)
    client = GymForgeAIClient(
        system_prompt=system,
        conversation_history=conv.conversation_history,
    )
    raw_reply = client.send_message(message)

    display_reply, show_disclaimer, storage_reply = _check_and_apply_disclaimer(raw_reply)

    # Persist — update last assistant message in history with storage_reply
    history = client.get_history()
    if history and history[-1]['role'] == 'assistant':
        history[-1]['content'] = storage_reply

    conv.conversation_history = history
    conv.last_message_at = timezone.now()
    conv.save(update_fields=['conversation_history', 'last_message_at'])

    return render(request, 'member/partials/ai_message.html', {
        'user_message': message,
        'reply': display_reply,
        'show_disclaimer': show_disclaimer,
        'disclaimer': SupplementRecommendation.SUPPLEMENT_DISCLAIMER,
        'session_type': session_type,
    })


@require_POST
@_member_required
def new_conversation(request):
    """Archive current conversation by starting a fresh one."""
    from apps.ai_coach.models import MemberAIConversation

    member_profile = _get_member_profile(request)
    if not member_profile:
        return redirect('members:register')

    session_type = request.POST.get('session_type',
                                    request.session.get('ai_session_type', 'general'))
    if session_type not in _SESSION_TYPE_SET:
        session_type = 'general'
    request.session['ai_session_type'] = session_type

    # Create a new (empty) conversation — old ones are preserved in the DB
    MemberAIConversation.objects.create(
        member=member_profile,
        session_type=session_type,
        conversation_history=[],
        started_at=timezone.now(),
    )
    return redirect(f'/app/ai/?type={session_type}')


@require_POST
@_member_required
def set_session_type(request):
    """Switch to a different session type and redirect to chat."""
    session_type = request.POST.get('session_type', 'general')
    if session_type not in _SESSION_TYPE_SET:
        session_type = 'general'
    request.session['ai_session_type'] = session_type
    return redirect(f'/app/ai/?type={session_type}')

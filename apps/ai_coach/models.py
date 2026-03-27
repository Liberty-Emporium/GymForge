from django.db import models


class MemberAIConversation(models.Model):
    """
    Persists the full conversation history between a member and their AI coach.

    One row per session. A new conversation is started when the member opens
    a new chat session; the previous one is closed (last_message_at stops updating).

    conversation_history stores the raw messages array passed to the Claude API:
    [
        {"role": "user",      "content": "How many calories should I eat?"},
        {"role": "assistant", "content": "Based on your goal of..."}
    ]

    session_type allows the AI to be invoked in different modes:
    - 'general'   → open-ended wellness chat
    - 'workout'   → focused on today's training
    - 'nutrition' → focused on meal and supplement questions
    - 'intake'    → guided health intake flow (Step 26); populates HealthProfile

    The system prompt is NOT stored here — it is assembled fresh at the start
    of each session from AISystemPrompt + HealthProfile + recent activity
    via build_member_context() (apps/ai_coach/context.py).
    """

    SESSION_TYPES = [
        ('general', 'General'),
        ('workout', 'Workout'),
        ('nutrition', 'Nutrition'),
        ('intake', 'Health Intake'),
    ]

    member = models.ForeignKey(
        'members.MemberProfile',
        on_delete=models.CASCADE,
        related_name='ai_conversations',
    )
    started_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now=True)
    # Raw messages array — format matches Anthropic Messages API
    conversation_history = models.JSONField(default=list)
    session_type = models.CharField(
        max_length=30,
        choices=SESSION_TYPES,
        default='general',
        db_index=True,
    )

    class Meta:
        ordering = ['-last_message_at']
        verbose_name = 'Member AI Conversation'
        verbose_name_plural = 'Member AI Conversations'

    def __str__(self):
        turns = len(self.conversation_history)
        return (
            f'{self.member.full_name} — '
            f'{self.get_session_type_display()} '
            f'({turns} turns) {self.started_at:%d %b %Y}'
        )

    @property
    def message_count(self):
        return len(self.conversation_history)

    @property
    def last_user_message(self):
        """Return the most recent user message text, or empty string."""
        for msg in reversed(self.conversation_history):
            if msg.get('role') == 'user':
                return msg.get('content', '')
        return ''


class OwnerAIConversation(models.Model):
    """
    Persists the full conversation history between a gym owner and their
    AI business assistant.

    conversation_history format:
    [
        {"role": "user",      "content": "Why are members churning?"},
        {"role": "assistant", "content": "Looking at your data..."}
    ]

    The system prompt is assembled from build_owner_context() which injects
    live business metrics at the start of each conversation.
    """

    owner = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='owner_ai_conversations',
    )
    started_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now=True)
    conversation_history = models.JSONField(default=list)

    class Meta:
        ordering = ['-last_message_at']
        verbose_name = 'Owner AI Conversation'
        verbose_name_plural = 'Owner AI Conversations'

    def __str__(self):
        turns = len(self.conversation_history)
        return (
            f'{self.owner.get_full_name()} — '
            f'Business chat ({turns} turns) {self.started_at:%d %b %Y}'
        )

    @property
    def message_count(self):
        return len(self.conversation_history)


class AISystemPrompt(models.Model):
    """
    Two-layer system prompt per prompt type (Section 9).

    base_content          → Platform Owner only. Core persona, topic
                            boundaries, disclaimers. Gym owners cannot
                            see or edit this layer.

    gym_additional_context → Gym Owner additions, appended after base_content.
                             Example: "We specialise in powerlifting",
                             "Our gym opens at 5am on weekdays."

    Final prompt sent to Claude = base_content + gym_additional_context.
    Use get_full_prompt() to obtain the merged string.

    unique=True on prompt_type enforces exactly one active prompt per type
    per tenant schema.
    """

    PROMPT_TYPES = [
        ('member_coach', 'Member AI Coach'),
        ('owner_assistant', 'Owner AI Assistant'),
    ]

    prompt_type = models.CharField(
        max_length=30,
        choices=PROMPT_TYPES,
        unique=True,
        db_index=True,
    )
    base_content = models.TextField()
    gym_additional_context = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'AI System Prompt'
        verbose_name_plural = 'AI System Prompts'

    def __str__(self):
        return (
            f'{self.get_prompt_type_display()} — '
            f'{"active" if self.is_active else "inactive"}'
        )

    def get_full_prompt(self):
        """
        Merge base_content and gym_additional_context into the final system prompt.
        Always returns at least base_content.
        """
        if self.gym_additional_context.strip():
            return f'{self.base_content}\n\n{self.gym_additional_context}'
        return self.base_content


class MemberAIAlert(models.Model):
    """
    An alert raised by the AI coach about a member's health or activity.

    Alert types
    -----------
    plateau    → workout metrics have stalled over consecutive sessions
    inactivity → member has not checked in for 14+ days
    concern    → member mentions a health concern during chat

    Surfaces in the trainer portal (Step 34) and owner dashboard (Step 22).
    Resolved by a staff member who acknowledges and acts on the alert.
    """

    ALERT_TYPES = [
        ('plateau', 'Plateau Detected'),
        ('inactivity', 'Inactivity'),
        ('concern', 'Health Concern'),
    ]

    member = models.ForeignKey(
        'members.MemberProfile',
        on_delete=models.CASCADE,
        related_name='ai_alerts',
    )
    alert_type = models.CharField(max_length=50, choices=ALERT_TYPES, db_index=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False, db_index=True)
    resolved_by = models.ForeignKey(
        'accounts.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='resolved_ai_alerts',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Member AI Alert'
        verbose_name_plural = 'Member AI Alerts'

    def __str__(self):
        status = 'resolved' if self.is_resolved else 'open'
        return (
            f'{self.member.full_name} — '
            f'{self.get_alert_type_display()} [{status}] '
            f'{self.created_at:%d %b %Y}'
        )

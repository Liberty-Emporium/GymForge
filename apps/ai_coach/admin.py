from django.contrib import admin
from django.utils.html import format_html

from .models import (
    AISystemPrompt,
    MemberAIAlert,
    MemberAIConversation,
    OwnerAIConversation,
)


# ---------------------------------------------------------------------------
# MemberAIConversation
# ---------------------------------------------------------------------------

@admin.register(MemberAIConversation)
class MemberAIConversationAdmin(admin.ModelAdmin):
    list_display = (
        'started_at', 'member', 'session_type', 'message_count',
        'last_message_at',
    )
    list_filter = ('session_type',)
    search_fields = ('member__user__first_name', 'member__user__last_name')
    ordering = ('-last_message_at',)
    readonly_fields = ('started_at', 'last_message_at', 'message_count_display')

    fieldsets = (
        ('Session', {
            'fields': ('member', 'session_type', 'started_at', 'last_message_at', 'message_count_display'),
        }),
        ('Conversation History', {
            'fields': ('conversation_history',),
            'classes': ('collapse',),
            'description': 'Raw JSON messages array as sent to the Claude API.',
        }),
    )

    def message_count(self, obj):
        return obj.message_count
    message_count.short_description = 'Messages'

    def message_count_display(self, obj):
        return obj.message_count
    message_count_display.short_description = 'Total messages'


# ---------------------------------------------------------------------------
# OwnerAIConversation
# ---------------------------------------------------------------------------

@admin.register(OwnerAIConversation)
class OwnerAIConversationAdmin(admin.ModelAdmin):
    list_display = ('started_at', 'owner', 'message_count', 'last_message_at')
    search_fields = ('owner__first_name', 'owner__last_name', 'owner__email')
    ordering = ('-last_message_at',)
    readonly_fields = ('started_at', 'last_message_at')

    fieldsets = (
        ('Session', {
            'fields': ('owner', 'started_at', 'last_message_at'),
        }),
        ('Conversation History', {
            'fields': ('conversation_history',),
            'classes': ('collapse',),
        }),
    )

    def message_count(self, obj):
        return obj.message_count
    message_count.short_description = 'Messages'


# ---------------------------------------------------------------------------
# AISystemPrompt
# ---------------------------------------------------------------------------

@admin.register(AISystemPrompt)
class AISystemPromptAdmin(admin.ModelAdmin):
    """
    Two-layer prompt editor.

    Platform Owner (platform_admin) can edit base_content.
    Gym Owner should only see/edit gym_additional_context — enforce via
    role-based admin access in the owner portal views (Step 22), not here.
    """

    list_display = ('prompt_type', 'is_active', 'base_length', 'context_length', 'updated_at')
    list_filter = ('prompt_type', 'is_active')
    ordering = ('prompt_type',)
    readonly_fields = ('updated_at', 'full_prompt_preview')

    fieldsets = (
        ('Prompt', {
            'fields': ('prompt_type', 'is_active', 'updated_at'),
        }),
        ('Base Content (Platform Owner)', {
            'fields': ('base_content',),
            'description': (
                'Core persona, topic boundaries, and safety rules. '
                'Gym owners cannot see or modify this section.'
            ),
        }),
        ('Gym Additional Context (Gym Owner)', {
            'fields': ('gym_additional_context',),
            'description': (
                'Gym-specific context appended after the base content. '
                'Example: "We specialise in powerlifting" or '
                '"Mention our 5am early-bird class on weekdays."'
            ),
        }),
        ('Full Prompt Preview', {
            'fields': ('full_prompt_preview',),
            'classes': ('collapse',),
        }),
    )

    def base_length(self, obj):
        return f'{len(obj.base_content)} chars'
    base_length.short_description = 'Base length'

    def context_length(self, obj):
        length = len(obj.gym_additional_context)
        return f'{length} chars' if length else '—'
    context_length.short_description = 'Gym context'

    def full_prompt_preview(self, obj):
        preview = obj.get_full_prompt()[:500]
        if len(obj.get_full_prompt()) > 500:
            preview += '…'
        return format_html(
            '<pre style="white-space:pre-wrap;font-size:12px;'
            'background:#f9fafb;padding:12px;border-radius:6px">{}</pre>',
            preview,
        )
    full_prompt_preview.short_description = 'Full prompt preview (first 500 chars)'


# ---------------------------------------------------------------------------
# MemberAIAlert
# ---------------------------------------------------------------------------

@admin.register(MemberAIAlert)
class MemberAIAlertAdmin(admin.ModelAdmin):
    list_display = (
        'created_at', 'member', 'alert_type_badge',
        'message_short', 'resolved_badge', 'resolved_by',
    )
    list_filter = ('alert_type', 'is_resolved')
    search_fields = ('member__user__first_name', 'member__user__last_name', 'message')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)

    fieldsets = (
        ('Alert', {
            'fields': ('member', 'alert_type', 'message', 'created_at'),
        }),
        ('Resolution', {
            'fields': ('is_resolved', 'resolved_by'),
        }),
    )

    def alert_type_badge(self, obj):
        colours = {
            'plateau': '#f59e0b',
            'inactivity': '#3b82f6',
            'concern': '#ef4444',
        }
        colour = colours.get(obj.alert_type, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            colour, obj.get_alert_type_display(),
        )
    alert_type_badge.short_description = 'Type'

    def message_short(self, obj):
        return obj.message[:80] + '…' if len(obj.message) > 80 else obj.message
    message_short.short_description = 'Message'

    def resolved_badge(self, obj):
        if obj.is_resolved:
            return format_html(
                '<span style="color:#10b981;font-weight:600">✓ Resolved</span>'
            )
        return format_html(
            '<span style="color:#ef4444;font-weight:600">Open</span>'
        )
    resolved_badge.short_description = 'Status'

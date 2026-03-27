"""
GymForge AI Client

Thin wrapper around the Anthropic Python SDK for the two AI features:
  - Member AI Coach        (session_type: general / workout / nutrition / intake)
  - Owner AI Assistant     (business intelligence and gym operations)

Usage
-----
from apps.ai_coach.client import GymForgeAIClient
from apps.ai_coach.context import build_member_context
from apps.ai_coach.prompts import render_member_prompt

context = build_member_context(member_profile)
system  = render_member_prompt(context)
history = conversation.conversation_history  # list from DB

client  = GymForgeAIClient(system_prompt=system, conversation_history=history)
reply   = client.send_message("What should I eat before training?")

# Persist updated history
conversation.conversation_history = client.get_history()
conversation.save(update_fields=['conversation_history'])
"""

import anthropic
from django.conf import settings


class GymForgeAIClient:
    """
    Stateful wrapper around the Anthropic Messages API.

    The system prompt is passed as the top-level `system` parameter
    (NOT as a message in the messages array) — this is the correct
    Anthropic API pattern and keeps it separate from the conversation history.

    conversation_history is a copy of the stored messages array and is
    updated in-memory with each round-trip. Callers must persist it back
    to the DB via get_history().

    Parameters
    ----------
    system_prompt : str
        The fully-rendered system prompt (base + gym context + member/owner data).
    conversation_history : list
        Existing messages in Anthropic format: [{"role": "...", "content": "..."}]
        Pass [] to start a fresh conversation.
    """

    MODEL = 'claude-opus-4-6'
    MAX_TOKENS = 1024

    def __init__(self, system_prompt: str, conversation_history: list):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.system_prompt = system_prompt
        # Work on a copy so the caller's list is not mutated until get_history()
        self.history = list(conversation_history)

    def send_message(self, user_message: str) -> str:
        """
        Append user_message to history, call Claude, append reply, return reply text.

        The system prompt is passed as the dedicated `system` parameter, never
        injected into the messages array. This matches Anthropic's recommended
        pattern and ensures the topic-boundary rules are always enforced.
        """
        self.history.append({'role': 'user', 'content': user_message})

        response = self.client.messages.create(
            model=self.MODEL,
            max_tokens=self.MAX_TOKENS,
            system=self.system_prompt,
            messages=self.history,
        )

        reply = response.content[0].text
        self.history.append({'role': 'assistant', 'content': reply})
        return reply

    def get_history(self) -> list:
        """
        Return the updated conversation history for DB persistence.

        Call this after send_message() and save the result to
        conversation.conversation_history.
        """
        return self.history

    def get_last_reply(self) -> str:
        """Return the most recent assistant message, or empty string."""
        for msg in reversed(self.history):
            if msg.get('role') == 'assistant':
                return msg.get('content', '')
        return ''

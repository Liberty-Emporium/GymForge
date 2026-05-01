"""Repair migration — ensures ai_coach tables exist on Railway Postgres."""
from django.db import migrations

SQL = """
CREATE TABLE IF NOT EXISTS "ai_coach_aisystemprompt" (
    "id"                      bigserial    PRIMARY KEY,
    "prompt_type"             varchar(30)  NOT NULL UNIQUE,
    "base_content"            text         NOT NULL DEFAULT '',
    "gym_additional_context"  text         NOT NULL DEFAULT '',
    "is_active"               boolean      NOT NULL DEFAULT true,
    "updated_at"              timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "ai_coach_memberaiconversation" (
    "id"                   bigserial   PRIMARY KEY,
    "started_at"           timestamptz NOT NULL DEFAULT now(),
    "last_message_at"      timestamptz NOT NULL DEFAULT now(),
    "conversation_history" jsonb       NOT NULL DEFAULT '[]',
    "session_type"         varchar(30) NOT NULL DEFAULT 'general',
    "member_id"            bigint      NULL
);

CREATE TABLE IF NOT EXISTS "ai_coach_memberaialert" (
    "id"            bigserial   PRIMARY KEY,
    "alert_type"    varchar(50) NOT NULL,
    "message"       text        NOT NULL DEFAULT '',
    "created_at"    timestamptz NOT NULL DEFAULT now(),
    "is_resolved"   boolean     NOT NULL DEFAULT false,
    "member_id"     bigint      NOT NULL,
    "resolved_by_id" bigint     NULL
);
"""

class Migration(migrations.Migration):
    dependencies = [
        ('ai_coach', '0001_initial'),
        ('members', '0004_ensure_tables'),
    ]
    operations = [migrations.RunSQL(SQL, reverse_sql='SELECT 1;')]

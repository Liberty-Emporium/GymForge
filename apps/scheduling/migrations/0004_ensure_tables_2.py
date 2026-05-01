"""Repair migration 2 — adds ClassSession, WorkoutPlan, Booking (real schema)."""
from django.db import migrations

SQL = """
CREATE TABLE IF NOT EXISTS "scheduling_classsession" (
    "id"                  bigserial    PRIMARY KEY,
    "start_datetime"      timestamptz  NOT NULL,
    "end_datetime"        timestamptz  NOT NULL,
    "capacity"            integer      NOT NULL DEFAULT 20,
    "is_cancelled"        boolean      NOT NULL DEFAULT false,
    "cancellation_reason" text         NOT NULL DEFAULT '',
    "session_notes"       text         NOT NULL DEFAULT '',
    "class_type_id"       bigint       NOT NULL,
    "location_id"         bigint       NOT NULL,
    "trainer_id"          bigint       NULL
);

CREATE TABLE IF NOT EXISTS "scheduling_workoutplan" (
    "id"            bigserial   PRIMARY KEY,
    "source"        varchar(20) NOT NULL DEFAULT 'trainer',
    "status"        varchar(20) NOT NULL DEFAULT 'draft',
    "plan_data"     jsonb       NOT NULL DEFAULT '{}',
    "created_at"    timestamptz NOT NULL DEFAULT now(),
    "approved_at"   timestamptz NULL,
    "created_by_id" bigint      NULL,
    "member_id"     bigint      NOT NULL
);

-- Drop the placeholder booking table from 0002 if it exists (wrong FK)
-- and replace with the correct one linked to class_session
DROP TABLE IF EXISTS "scheduling_booking" CASCADE;

CREATE TABLE IF NOT EXISTS "scheduling_booking" (
    "id"                  bigserial   PRIMARY KEY,
    "status"              varchar(20) NOT NULL DEFAULT 'confirmed',
    "booked_at"           timestamptz NOT NULL DEFAULT now(),
    "cancelled_at"        timestamptz NULL,
    "waitlist_position"   integer     NULL,
    "no_show_fee_charged" boolean     NOT NULL DEFAULT false,
    "member_id"           bigint      NOT NULL,
    "class_session_id"    bigint      NOT NULL,
    UNIQUE ("member_id", "class_session_id")
);

-- Waitlist linked to class_session
DROP TABLE IF EXISTS "scheduling_waitlist" CASCADE;
CREATE TABLE IF NOT EXISTS "scheduling_waitlist" (
    "id"               bigserial   PRIMARY KEY,
    "joined_at"        timestamptz NOT NULL DEFAULT now(),
    "notified"         boolean     NOT NULL DEFAULT false,
    "member_id"        bigint      NULL,
    "class_session_id" bigint      NOT NULL
);
"""

class Migration(migrations.Migration):
    dependencies = [
        ('scheduling', '0003_ensure_tables_2'),
        ('members', '0004_ensure_tables'),
    ]
    operations = [migrations.RunSQL(SQL, reverse_sql='SELECT 1;')]

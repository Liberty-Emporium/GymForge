"""Repair migration 2 — adds remaining checkin tables (Shift, CleaningTask etc)."""
from django.db import migrations

SQL = """
CREATE TABLE IF NOT EXISTS "checkin_cardscanlog" (
    "id"          bigserial   PRIMARY KEY,
    "scanned_at"  timestamptz NOT NULL DEFAULT now(),
    "result"      varchar(20) NOT NULL DEFAULT 'granted',
    "card_id"     bigint      NULL,
    "device_id"   bigint      NULL
);

CREATE TABLE IF NOT EXISTS "checkin_membernote" (
    "id"         bigserial    PRIMARY KEY,
    "content"    text         NOT NULL DEFAULT '',
    "created_at" timestamptz  NOT NULL DEFAULT now(),
    "is_pinned"  boolean      NOT NULL DEFAULT false,
    "author_id"  bigint       NOT NULL,
    "member_id"  bigint       NOT NULL
);

CREATE TABLE IF NOT EXISTS "checkin_shift" (
    "id"          bigserial    PRIMARY KEY,
    "date"        date         NOT NULL,
    "start_time"  time         NOT NULL,
    "end_time"    time         NOT NULL,
    "status"      varchar(20)  NOT NULL DEFAULT 'scheduled',
    "notes"       text         NOT NULL DEFAULT '',
    "location_id" bigint       NOT NULL,
    "staff_id"    bigint       NOT NULL
);

CREATE TABLE IF NOT EXISTS "checkin_staffrequest" (
    "id"               bigserial    PRIMARY KEY,
    "request_type"     varchar(20)  NOT NULL DEFAULT 'time_off',
    "start_date"       date         NOT NULL,
    "end_date"         date         NOT NULL,
    "reason"           text         NOT NULL DEFAULT '',
    "status"           varchar(20)  NOT NULL DEFAULT 'pending',
    "reviewed_at"      timestamptz  NULL,
    "location_id"      bigint       NULL,
    "requested_by_id"  bigint       NOT NULL,
    "reviewed_by_id"   bigint       NULL
);

CREATE TABLE IF NOT EXISTS "checkin_tasktemplate" (
    "id"          bigserial    PRIMARY KEY,
    "name"        varchar(200) NOT NULL,
    "description" text         NOT NULL DEFAULT '',
    "frequency"   varchar(20)  NOT NULL DEFAULT 'daily',
    "priority"    varchar(10)  NOT NULL DEFAULT 'medium',
    "is_active"   boolean      NOT NULL DEFAULT true,
    "location_id" bigint       NOT NULL
);

CREATE TABLE IF NOT EXISTS "checkin_cleaningtask" (
    "id"             bigserial   PRIMARY KEY,
    "shift_date"     date        NOT NULL DEFAULT now(),
    "completed"      boolean     NOT NULL DEFAULT false,
    "completed_at"   timestamptz NULL,
    "notes"          text        NOT NULL DEFAULT '',
    "assigned_to_id" bigint      NOT NULL,
    "template_id"    bigint      NOT NULL
);

CREATE TABLE IF NOT EXISTS "checkin_trainerprofile" (
    "id"                   bigserial    PRIMARY KEY,
    "bio"                  text         NOT NULL DEFAULT '',
    "specializations"      text         NOT NULL DEFAULT '',
    "certifications"       text         NOT NULL DEFAULT '',
    "profile_photo"        varchar(100) NOT NULL DEFAULT '',
    "is_accepting_clients" boolean      NOT NULL DEFAULT true,
    "user_id"              bigint       NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS "checkin_accessrule" (
    "id"                 bigserial   PRIMARY KEY,
    "can_access"         boolean     NOT NULL DEFAULT true,
    "location_id"        bigint      NOT NULL,
    "membership_tier_id" bigint      NOT NULL
);

CREATE TABLE IF NOT EXISTS "checkin_clientassignment" (
    "id"          bigserial   PRIMARY KEY,
    "assigned_at" timestamptz NOT NULL DEFAULT now(),
    "is_active"   boolean     NOT NULL DEFAULT true,
    "member_id"   bigint      NOT NULL,
    "staff_id"    bigint      NOT NULL
);
"""

class Migration(migrations.Migration):
    dependencies = [
        ('checkin', '0002_ensure_tables'),
        ('members', '0004_ensure_tables'),
    ]
    operations = [migrations.RunSQL(SQL, reverse_sql='SELECT 1;')]

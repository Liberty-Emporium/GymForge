"""Repair migration — ensures checkin tables exist on Railway Postgres."""
from django.db import migrations

SQL = """
CREATE TABLE IF NOT EXISTS "checkin_doordevice" (
    "id"           bigserial    PRIMARY KEY,
    "name"         varchar(100) NOT NULL,
    "device_type"  varchar(20)  NOT NULL DEFAULT 'entrance',
    "device_token" varchar(100) NOT NULL UNIQUE DEFAULT '',
    "is_active"    boolean      NOT NULL DEFAULT true,
    "last_seen"    timestamptz  NULL,
    "ip_address"   inet         NULL,
    "location_id"  bigint       NULL
);

CREATE TABLE IF NOT EXISTS "checkin_membercard" (
    "id"           bigserial    PRIMARY KEY,
    "card_uid"     varchar(100) NOT NULL UNIQUE,
    "card_type"    varchar(20)  NOT NULL DEFAULT 'rfid',
    "is_active"    boolean      NOT NULL DEFAULT true,
    "issued_at"    timestamptz  NOT NULL DEFAULT now(),
    "member_id"    bigint       NULL
);

CREATE TABLE IF NOT EXISTS "checkin_checkin" (
    "id"              bigserial   PRIMARY KEY,
    "checked_in_at"   timestamptz NOT NULL DEFAULT now(),
    "checked_out_at"  timestamptz NULL,
    "method"          varchar(20) NOT NULL DEFAULT 'manual',
    "is_guest"        boolean     NOT NULL DEFAULT false,
    "checked_in_by_id" bigint     NULL,
    "location_id"     bigint      NULL,
    "member_id"       bigint      NULL
);

CREATE TABLE IF NOT EXISTS "checkin_lockerassignment" (
    "id"           bigserial    PRIMARY KEY,
    "locker_number" varchar(20) NOT NULL,
    "assigned_at"  timestamptz  NOT NULL DEFAULT now(),
    "released_at"  timestamptz  NULL,
    "member_id"    bigint       NULL
);
"""

class Migration(migrations.Migration):
    dependencies = [
        ('checkin', '0001_initial'),
        ('members', '0004_ensure_tables'),
    ]
    operations = [migrations.RunSQL(SQL, reverse_sql='SELECT 1;')]

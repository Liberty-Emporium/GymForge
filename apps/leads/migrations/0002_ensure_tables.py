"""Repair migration — ensures leads tables exist on Railway Postgres."""
from django.db import migrations

SQL = """
CREATE TABLE IF NOT EXISTS "leads_lead" (
    "id"                bigserial    PRIMARY KEY,
    "first_name"        varchar(100) NOT NULL,
    "last_name"         varchar(100) NOT NULL,
    "email"             varchar(254) NOT NULL DEFAULT '',
    "phone"             varchar(20)  NOT NULL DEFAULT '',
    "source"            varchar(20)  NOT NULL DEFAULT 'walk_in',
    "status"            varchar(20)  NOT NULL DEFAULT 'new',
    "notes"             text         NOT NULL DEFAULT '',
    "created_at"        timestamptz  NOT NULL DEFAULT now(),
    "last_contacted_at" timestamptz  NULL,
    "converted_at"      timestamptz  NULL,
    "assigned_to_id"    bigint       NULL,
    "location_id"       bigint       NULL
);

CREATE TABLE IF NOT EXISTS "leads_leadfollowup" (
    "id"            bigserial    PRIMARY KEY,
    "scheduled_at"  timestamptz  NOT NULL,
    "completed_at"  timestamptz  NULL,
    "method"        varchar(20)  NOT NULL DEFAULT 'email',
    "notes"         text         NOT NULL DEFAULT '',
    "completed_by_id" bigint     NULL,
    "lead_id"       bigint       NOT NULL REFERENCES "leads_lead"("id") ON DELETE CASCADE
);
"""

class Migration(migrations.Migration):
    dependencies = [('leads', '0001_initial')]
    operations = [migrations.RunSQL(SQL, reverse_sql='SELECT 1;')]

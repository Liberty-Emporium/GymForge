"""
Repair migration — ensures platform_admin tables exist on Railway Postgres.
"""
from django.db import migrations

SQL = """
CREATE TABLE IF NOT EXISTS "platform_admin_auditlog" (
    "id"           bigserial    PRIMARY KEY,
    "actor_email"  varchar(254) NOT NULL,
    "gym_schema"   varchar(100) NOT NULL DEFAULT '',
    "action"       varchar(200) NOT NULL,
    "target_model" varchar(100) NOT NULL DEFAULT '',
    "target_id"    integer      NULL,
    "details"      jsonb        NOT NULL DEFAULT '{}',
    "timestamp"    timestamptz  NOT NULL DEFAULT now(),
    "ip_address"   inet         NULL
);

CREATE TABLE IF NOT EXISTS "platform_admin_plan" (
    "id"             bigserial    PRIMARY KEY,
    "name"           varchar(100) NOT NULL,
    "max_members"    integer      NOT NULL,
    "max_locations"  integer      NOT NULL,
    "price_monthly"  numeric(8,2) NOT NULL,
    "stripe_price_id" varchar(100) NOT NULL,
    "features"       jsonb        NOT NULL DEFAULT '{}',
    "is_active"      boolean      NOT NULL DEFAULT true
);
"""


class Migration(migrations.Migration):

    dependencies = [
        ('platform_admin', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(SQL, reverse_sql='SELECT 1;'),
    ]

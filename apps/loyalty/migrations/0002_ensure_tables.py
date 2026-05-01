"""
Repair migration — ensures loyalty tables exist on Railway Postgres
even when stale migration records mark 0001_initial as already applied.
"""
from django.db import migrations

SQL = """
CREATE TABLE IF NOT EXISTS "loyalty_loyaltyrule" (
    "id"          bigserial    PRIMARY KEY,
    "action"      varchar(30)  NOT NULL UNIQUE,
    "points"      integer      NOT NULL DEFAULT 0,
    "description" varchar(255) NOT NULL DEFAULT '',
    "is_active"   boolean      NOT NULL DEFAULT true,
    "max_per_day" integer      NULL
);

CREATE TABLE IF NOT EXISTS "loyalty_badgemilestone" (
    "id"          bigserial    PRIMARY KEY,
    "name"        varchar(200) NOT NULL,
    "description" text         NOT NULL DEFAULT '',
    "icon"        varchar(100) NOT NULL DEFAULT '',
    "threshold"   integer      NOT NULL DEFAULT 0,
    "badge_type"  varchar(30)  NOT NULL DEFAULT 'custom',
    "is_active"   boolean      NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS "loyalty_loyaltyreward" (
    "id"           bigserial    PRIMARY KEY,
    "name"         varchar(200) NOT NULL,
    "description"  text         NOT NULL DEFAULT '',
    "points_cost"  integer      NOT NULL DEFAULT 0,
    "reward_type"  varchar(30)  NOT NULL DEFAULT 'discount',
    "value"        numeric(8,2) NOT NULL DEFAULT 0.00,
    "is_active"    boolean      NOT NULL DEFAULT true,
    "stock"        integer      NULL
);

CREATE TABLE IF NOT EXISTS "loyalty_memberpoints" (
    "id"              bigserial   PRIMARY KEY,
    "total_points"    integer     NOT NULL DEFAULT 0,
    "lifetime_points" integer     NOT NULL DEFAULT 0,
    "member_id"       bigint      NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS "loyalty_loyaltytransaction" (
    "id"               bigserial    PRIMARY KEY,
    "points"           integer      NOT NULL,
    "transaction_type" varchar(10)  NOT NULL DEFAULT 'earn',
    "action"           varchar(30)  NOT NULL DEFAULT '',
    "description"      varchar(255) NOT NULL DEFAULT '',
    "created_at"       timestamptz  NOT NULL DEFAULT now(),
    "member_id"        bigint       NULL,
    "reward_id"        bigint       NULL REFERENCES "loyalty_loyaltyreward"("id") ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS "loyalty_memberbadge" (
    "id"         bigserial   PRIMARY KEY,
    "earned_at"  timestamptz NOT NULL DEFAULT now(),
    "badge_id"   bigint      NULL REFERENCES "loyalty_badgemilestone"("id") ON DELETE CASCADE,
    "member_id"  bigint      NULL
);
"""


class Migration(migrations.Migration):

    dependencies = [
        ('loyalty', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(SQL, reverse_sql='SELECT 1;'),
    ]

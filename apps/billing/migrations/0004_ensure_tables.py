"""
Repair migration — ensures billing tables exist even if the Railway Postgres DB
has stale migration records (older migrations marked applied but tables absent).
Uses CREATE TABLE IF NOT EXISTS so it is always safe to re-run.
"""
from django.db import migrations


CREATE_MEMBERSHIPTIER = """
CREATE TABLE IF NOT EXISTS "billing_membershiptier" (
    "id"                          bigserial    PRIMARY KEY,
    "name"                        varchar(200) NOT NULL,
    "price"                       numeric(8,2) NOT NULL,
    "billing_cycle"               varchar(20)  NOT NULL,
    "description"                 text         NOT NULL DEFAULT '',
    "is_active"                   boolean      NOT NULL DEFAULT true,
    "trial_days"                  integer      NOT NULL DEFAULT 0,
    "cancellation_window_hours"   integer      NOT NULL DEFAULT 2,
    "no_show_fee"                 numeric(6,2) NOT NULL DEFAULT 0.00,
    "late_cancel_fee"             numeric(6,2) NOT NULL DEFAULT 0.00
);
"""

CREATE_MEMBERSHIPTIER_SERVICES = """
CREATE TABLE IF NOT EXISTS "billing_membershiptier_included_services" (
    "id"              bigserial PRIMARY KEY,
    "membershiptier_id" bigint NOT NULL REFERENCES "billing_membershiptier"("id") ON DELETE CASCADE,
    "service_id"      bigint NOT NULL REFERENCES "core_service"("id") ON DELETE CASCADE,
    UNIQUE ("membershiptier_id", "service_id")
);
"""

CREATE_MEMBERMEMBERSHIP = """
CREATE TABLE IF NOT EXISTS "billing_membermembership" (
    "id"                     bigserial    PRIMARY KEY,
    "start_date"             date         NOT NULL,
    "end_date"               date         NULL,
    "status"                 varchar(20)  NOT NULL DEFAULT 'active',
    "stripe_subscription_id" varchar(100) NOT NULL DEFAULT '',
    "stripe_customer_id"     varchar(100) NOT NULL DEFAULT '',
    "grace_period_days"      integer      NOT NULL DEFAULT 3,
    "overdue_since"          timestamptz  NULL,
    "member_id"              bigint       NULL,
    "tier_id"                bigint       NULL REFERENCES "billing_membershiptier"("id") ON DELETE CASCADE
);
"""

CREATE_MEMBERTAB = """
CREATE TABLE IF NOT EXISTS "billing_membertab" (
    "id"             bigserial    PRIMARY KEY,
    "balance"        numeric(8,2) NOT NULL DEFAULT 0.00,
    "spending_limit" numeric(8,2) NOT NULL DEFAULT 100.00,
    "last_charged"   timestamptz  NULL,
    "member_id"      bigint       NULL
);
"""

CREATE_CARDPURCHASE = """
CREATE TABLE IF NOT EXISTS "billing_cardpurchase" (
    "id"                     bigserial    PRIMARY KEY,
    "item_description"       varchar(200) NOT NULL,
    "amount"                 numeric(8,2) NOT NULL,
    "processed_at"           timestamptz  NOT NULL DEFAULT now(),
    "stripe_payment_intent"  varchar(100) NOT NULL DEFAULT '',
    "status"                 varchar(20)  NOT NULL DEFAULT 'completed',
    "card_id"                bigint       NULL,
    "device_id"              bigint       NULL
);
"""

CREATE_NOSHOWCHARGE = """
CREATE TABLE IF NOT EXISTS "billing_noshowcharge" (
    "id"                     bigserial    PRIMARY KEY,
    "amount"                 numeric(6,2) NOT NULL,
    "charge_type"            varchar(20)  NOT NULL,
    "stripe_payment_intent"  varchar(100) NOT NULL DEFAULT '',
    "charged_at"             timestamptz  NOT NULL DEFAULT now(),
    "status"                 varchar(20)  NOT NULL DEFAULT 'completed',
    "booking_id"             bigint       NULL,
    "member_id"              bigint       NULL
);
"""


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0003_membermembership_stripe_customer_id'),
        ('core', '0002_ensure_tables'),
    ]

    operations = [
        migrations.RunSQL(CREATE_MEMBERSHIPTIER,   reverse_sql='DROP TABLE IF EXISTS "billing_membershiptier" CASCADE;'),
        migrations.RunSQL(CREATE_MEMBERSHIPTIER_SERVICES, reverse_sql='DROP TABLE IF EXISTS "billing_membershiptier_included_services";'),
        migrations.RunSQL(CREATE_MEMBERMEMBERSHIP, reverse_sql='DROP TABLE IF EXISTS "billing_membermembership";'),
        migrations.RunSQL(CREATE_MEMBERTAB,        reverse_sql='DROP TABLE IF EXISTS "billing_membertab";'),
        migrations.RunSQL(CREATE_CARDPURCHASE,     reverse_sql='DROP TABLE IF EXISTS "billing_cardpurchase";'),
        migrations.RunSQL(CREATE_NOSHOWCHARGE,     reverse_sql='DROP TABLE IF EXISTS "billing_noshowcharge";'),
    ]

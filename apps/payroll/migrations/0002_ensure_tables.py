"""Repair migration — ensures payroll tables exist on Railway Postgres."""
from django.db import migrations

SQL = """
CREATE TABLE IF NOT EXISTS "payroll_payrollperiod" (
    "id"            bigserial    PRIMARY KEY,
    "period_start"  date         NOT NULL,
    "period_end"    date         NOT NULL,
    "status"        varchar(10)  NOT NULL DEFAULT 'draft',
    "summary"       jsonb        NOT NULL DEFAULT '{}',
    "total_payout"  numeric(10,2) NOT NULL DEFAULT 0,
    "approved_at"   timestamptz  NULL,
    "created_at"    timestamptz  NOT NULL DEFAULT now(),
    "notes"         text         NOT NULL DEFAULT '',
    "approved_by_id" bigint      NULL
);

CREATE TABLE IF NOT EXISTS "payroll_staffpayrate" (
    "id"             bigserial    PRIMARY KEY,
    "pay_type"       varchar(15)  NOT NULL DEFAULT 'hourly',
    "rate"           numeric(8,2) NOT NULL,
    "effective_from" date         NOT NULL,
    "effective_to"   date         NULL,
    "notes"          text         NOT NULL DEFAULT '',
    "location_id"    bigint       NULL,
    "staff_id"       bigint       NOT NULL
);
"""

class Migration(migrations.Migration):
    dependencies = [('payroll', '0001_initial')]
    operations = [migrations.RunSQL(SQL, reverse_sql='SELECT 1;')]

"""Repair migration — ensures shop tables exist on Railway Postgres."""
from django.db import migrations

SQL = """
CREATE TABLE IF NOT EXISTS "shop_shopproduct" (
    "id"                    bigserial    PRIMARY KEY,
    "name"                  varchar(200) NOT NULL,
    "description"           text         NOT NULL DEFAULT '',
    "category"              varchar(20)  NOT NULL DEFAULT 'other',
    "price"                 numeric(8,2) NOT NULL,
    "stock"                 integer      NOT NULL DEFAULT 0,
    "sku"                   varchar(100) NOT NULL DEFAULT '',
    "image"                 varchar(100) NOT NULL DEFAULT '',
    "is_active"             boolean      NOT NULL DEFAULT true,
    "loyalty_points_earned" integer      NOT NULL DEFAULT 0,
    "created_at"            timestamptz  NOT NULL DEFAULT now(),
    "updated_at"            timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "shop_shoporder" (
    "id"                   bigserial    PRIMARY KEY,
    "items"                jsonb        NOT NULL DEFAULT '[]',
    "total_amount"         numeric(8,2) NOT NULL,
    "payment_method"       varchar(10)  NOT NULL DEFAULT 'card',
    "status"               varchar(10)  NOT NULL DEFAULT 'pending',
    "stripe_payment_intent" varchar(255) NOT NULL DEFAULT '',
    "loyalty_points_used"  integer      NOT NULL DEFAULT 0,
    "loyalty_points_earned" integer     NOT NULL DEFAULT 0,
    "notes"                text         NOT NULL DEFAULT '',
    "ordered_at"           timestamptz  NOT NULL DEFAULT now(),
    "member_id"            bigint       NULL,
    "processed_by_id"      bigint       NULL
);
"""

class Migration(migrations.Migration):
    dependencies = [
        ('shop', '0001_initial'),
        ('members', '0004_ensure_tables'),
    ]
    operations = [migrations.RunSQL(SQL, reverse_sql='SELECT 1;')]

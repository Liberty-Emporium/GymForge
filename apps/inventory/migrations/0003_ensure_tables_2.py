"""Repair migration 2 — adds SupplyRequest and SupplyItem (missing from first run)."""
from django.db import migrations

SQL = """
CREATE TABLE IF NOT EXISTS "inventory_supplyitem" (
    "id"             bigserial    PRIMARY KEY,
    "name"           varchar(200) NOT NULL,
    "category"       varchar(30)  NOT NULL DEFAULT 'other',
    "unit"           varchar(30)  NOT NULL DEFAULT 'each',
    "current_stock"  integer      NOT NULL DEFAULT 0,
    "minimum_stock"  integer      NOT NULL DEFAULT 0,
    "is_active"      boolean      NOT NULL DEFAULT true,
    "last_restocked" date         NULL,
    "notes"          text         NOT NULL DEFAULT '',
    "location_id"    bigint       NULL
);

CREATE TABLE IF NOT EXISTS "inventory_supplyrequest" (
    "id"              bigserial   PRIMARY KEY,
    "quantity"        integer     NOT NULL DEFAULT 1,
    "status"          varchar(10) NOT NULL DEFAULT 'pending',
    "notes"           text        NOT NULL DEFAULT '',
    "created_at"      timestamptz NOT NULL DEFAULT now(),
    "updated_at"      timestamptz NOT NULL DEFAULT now(),
    "received_at"     timestamptz NULL,
    "approved_by_id"  bigint      NULL,
    "requested_by_id" bigint      NULL,
    "supply_item_id"  bigint      NOT NULL
);
"""

class Migration(migrations.Migration):
    dependencies = [('inventory', '0002_ensure_tables')]
    operations = [migrations.RunSQL(SQL, reverse_sql='SELECT 1;')]

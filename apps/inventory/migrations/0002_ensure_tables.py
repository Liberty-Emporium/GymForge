"""Repair migration — ensures inventory tables exist on Railway Postgres."""
from django.db import migrations

SQL = """
CREATE TABLE IF NOT EXISTS "inventory_equipment" (
    "id"               bigserial     PRIMARY KEY,
    "name"             varchar(200)  NOT NULL,
    "description"      text          NOT NULL DEFAULT '',
    "serial_number"    varchar(100)  NOT NULL DEFAULT '',
    "purchase_date"    date          NULL,
    "purchase_price"   numeric(10,2) NULL,
    "condition"        varchar(20)   NOT NULL DEFAULT 'good',
    "last_serviced"    date          NULL,
    "next_service_due" date          NULL,
    "image"            varchar(100)  NOT NULL DEFAULT '',
    "is_active"        boolean       NOT NULL DEFAULT true,
    "notes"            text          NOT NULL DEFAULT '',
    "created_at"       timestamptz   NOT NULL DEFAULT now(),
    "location_id"      bigint        NULL
);

CREATE TABLE IF NOT EXISTS "inventory_maintenanceticket" (
    "id"               bigserial    PRIMARY KEY,
    "title"            varchar(200) NOT NULL,
    "description"      text         NOT NULL DEFAULT '',
    "priority"         varchar(10)  NOT NULL DEFAULT 'medium',
    "status"           varchar(15)  NOT NULL DEFAULT 'open',
    "photo"            varchar(100) NOT NULL DEFAULT '',
    "resolution_notes" text         NOT NULL DEFAULT '',
    "created_at"       timestamptz  NOT NULL DEFAULT now(),
    "updated_at"       timestamptz  NOT NULL DEFAULT now(),
    "resolved_at"      timestamptz  NULL,
    "assigned_to_id"   bigint       NULL,
    "equipment_id"     bigint       NULL REFERENCES "inventory_equipment"("id") ON DELETE SET NULL,
    "location_id"      bigint       NULL,
    "reported_by_id"   bigint       NULL
);

CREATE TABLE IF NOT EXISTS "inventory_supplyitem" (
    "id"             bigserial    PRIMARY KEY,
    "name"           varchar(200) NOT NULL,
    "category"       varchar(30)  NOT NULL DEFAULT 'other',
    "unit"           varchar(30)  NOT NULL DEFAULT 'each',
    "current_stock"  integer      NOT NULL DEFAULT 0,
    "minimum_stock"  integer      NOT NULL DEFAULT 0,
    "last_restocked" date         NULL,
    "notes"          text         NOT NULL DEFAULT '',
    "location_id"    bigint       NULL
);

CREATE TABLE IF NOT EXISTS "inventory_supplyrequest" (
    "id"              bigserial   PRIMARY KEY,
    "quantity"        integer     NOT NULL,
    "status"          varchar(10) NOT NULL DEFAULT 'pending',
    "notes"           text        NOT NULL DEFAULT '',
    "created_at"      timestamptz NOT NULL DEFAULT now(),
    "updated_at"      timestamptz NOT NULL DEFAULT now(),
    "received_at"     timestamptz NULL,
    "approved_by_id"  bigint      NULL,
    "requested_by_id" bigint      NULL,
    "supply_item_id"  bigint      NOT NULL REFERENCES "inventory_supplyitem"("id") ON DELETE CASCADE
);
"""

class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0001_initial'),
        ('core', '0002_ensure_tables'),
    ]
    operations = [migrations.RunSQL(SQL, reverse_sql='SELECT 1;')]

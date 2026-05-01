"""Repair migration — ensures ClassSession and Booking tables exist."""
from django.db import migrations

SQL = """
CREATE TABLE IF NOT EXISTS "scheduling_classsession" (
    "id"                    bigserial    PRIMARY KEY,
    "start_datetime"        timestamptz  NOT NULL,
    "end_datetime"          timestamptz  NOT NULL,
    "capacity"              integer      NOT NULL DEFAULT 20,
    "is_cancelled"          boolean      NOT NULL DEFAULT false,
    "cancellation_reason"   text         NOT NULL DEFAULT '',
    "session_notes"         text         NOT NULL DEFAULT '',
    "class_type_id"         bigint       NOT NULL REFERENCES "scheduling_classtype"("id") ON DELETE CASCADE,
    "location_id"           bigint       NOT NULL,
    "trainer_id"            bigint       NULL
);

CREATE TABLE IF NOT EXISTS "scheduling_booking" (
    "id"                    bigserial   PRIMARY KEY,
    "status"                varchar(20) NOT NULL DEFAULT 'confirmed',
    "booked_at"             timestamptz NOT NULL DEFAULT now(),
    "cancelled_at"          timestamptz NULL,
    "waitlist_position"     integer     NULL,
    "no_show_fee_charged"   boolean     NOT NULL DEFAULT false,
    "member_id"             bigint      NOT NULL,
    "class_session_id"      bigint      NOT NULL REFERENCES "scheduling_classsession"("id") ON DELETE CASCADE,
    UNIQUE ("member_id", "class_session_id")
);
"""

class Migration(migrations.Migration):
    dependencies = [
        ('scheduling', '0002_ensure_tables'),
        ('members', '0004_ensure_tables'),
    ]
    operations = [migrations.RunSQL(SQL, reverse_sql='SELECT 1;')]

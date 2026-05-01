"""
Column repair migration — adds any missing columns to existing tables.
Uses ALTER TABLE ... ADD COLUMN IF NOT EXISTS (Postgres 9.6+).

Fixes cases where CREATE TABLE IF NOT EXISTS ran without a column,
then later CREATE TABLE IF NOT EXISTS was a no-op (table already existed).
"""
from django.db import migrations


SQL = """
-- inventory_supplyitem missing is_active (was added in 0003 but table already existed from 0002)
ALTER TABLE inventory_supplyitem ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;

-- checkin_shift missing is_active column if it exists
ALTER TABLE checkin_shift ADD COLUMN IF NOT EXISTS status varchar(20) NOT NULL DEFAULT 'scheduled';

-- members_memberprofile — ensure all migration-added columns exist
ALTER TABLE members_memberprofile ADD COLUMN IF NOT EXISTS pin_hash varchar(128) NOT NULL DEFAULT '';
ALTER TABLE members_memberprofile ADD COLUMN IF NOT EXISTS fcm_token varchar(512) NOT NULL DEFAULT '';

-- billing_membermembership stripe_customer_id (migration 0003 adds this)
ALTER TABLE billing_membermembership ADD COLUMN IF NOT EXISTS stripe_customer_id varchar(100) NOT NULL DEFAULT '';

-- checkin_membercard issued_by_id
ALTER TABLE checkin_membercard ADD COLUMN IF NOT EXISTS issued_by_id bigint NULL;

-- scheduling_classsession
ALTER TABLE scheduling_classsession ADD COLUMN IF NOT EXISTS session_notes text NOT NULL DEFAULT '';
ALTER TABLE scheduling_classsession ADD COLUMN IF NOT EXISTS cancellation_reason text NOT NULL DEFAULT '';

-- scheduling_booking (older version may be linked to class_schedule not class_session)
-- Drop and recreate if linked to wrong parent
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'scheduling_booking'
        AND column_name = 'schedule_id'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'scheduling_booking'
        AND column_name = 'class_session_id'
    ) THEN
        ALTER TABLE scheduling_booking RENAME COLUMN schedule_id TO class_session_id;
        ALTER TABLE scheduling_booking ADD COLUMN IF NOT EXISTS cancelled_at timestamptz NULL;
        ALTER TABLE scheduling_booking ADD COLUMN IF NOT EXISTS waitlist_position integer NULL;
        ALTER TABLE scheduling_booking ADD COLUMN IF NOT EXISTS no_show_fee_charged boolean NOT NULL DEFAULT false;
    END IF;
END $$;

-- Add class_session_id if completely missing (table built without it)
ALTER TABLE scheduling_booking ADD COLUMN IF NOT EXISTS class_session_id bigint NULL;
ALTER TABLE scheduling_booking ADD COLUMN IF NOT EXISTS cancelled_at timestamptz NULL;
ALTER TABLE scheduling_booking ADD COLUMN IF NOT EXISTS waitlist_position integer NULL;
ALTER TABLE scheduling_booking ADD COLUMN IF NOT EXISTS no_show_fee_charged boolean NOT NULL DEFAULT false;

-- scheduling_waitlist
ALTER TABLE scheduling_waitlist ADD COLUMN IF NOT EXISTS class_session_id bigint NULL;

-- community tables
ALTER TABLE community_communitypost ADD COLUMN IF NOT EXISTS likes_count integer NOT NULL DEFAULT 0;

-- leads
ALTER TABLE leads_lead ADD COLUMN IF NOT EXISTS interest_level varchar(20) NOT NULL DEFAULT 'medium';

-- loyalty_memberpoints (may not exist via nuclear migration if model wasn't found)
CREATE TABLE IF NOT EXISTS loyalty_memberpoints (
    id               bigserial PRIMARY KEY,
    total_points     integer NOT NULL DEFAULT 0,
    lifetime_points  integer NOT NULL DEFAULT 0,
    member_id        bigint  NULL UNIQUE
);
"""


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0003_create_all_missing_tables'),
    ]
    operations = [
        migrations.RunSQL(SQL, reverse_sql='SELECT 1;'),
    ]

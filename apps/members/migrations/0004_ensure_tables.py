"""Repair migration — ensures members tables exist on Railway Postgres."""
from django.db import migrations

SQL = """
CREATE TABLE IF NOT EXISTS "members_familyaccount" (
    "id"         bigserial    PRIMARY KEY,
    "name"       varchar(200) NOT NULL,
    "created_at" timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "members_memberprofile" (
    "id"                       bigserial    PRIMARY KEY,
    "date_of_birth"            date         NULL,
    "emergency_contact_name"   varchar(200) NOT NULL DEFAULT '',
    "emergency_contact_phone"  varchar(20)  NOT NULL DEFAULT '',
    "join_date"                date         NOT NULL DEFAULT now(),
    "waiver_signed"            boolean      NOT NULL DEFAULT false,
    "waiver_signed_at"         timestamptz  NULL,
    "loyalty_points"           integer      NOT NULL DEFAULT 0,
    "referral_code"            varchar(20)  NOT NULL UNIQUE DEFAULT '',
    "pin_hash"                 varchar(128) NOT NULL DEFAULT '',
    "fcm_token"                varchar(512) NOT NULL DEFAULT '',
    "family_account_id"        bigint       NULL REFERENCES "members_familyaccount"("id") ON DELETE SET NULL,
    "primary_location_id"      bigint       NULL,
    "referred_by_id"           bigint       NULL REFERENCES "members_memberprofile"("id") ON DELETE SET NULL,
    "user_id"                  bigint       NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS "members_healthprofile" (
    "id"                  bigserial    PRIMARY KEY,
    "fitness_goal"        varchar(100) NOT NULL DEFAULT '',
    "goal_detail"         text         NOT NULL DEFAULT '',
    "goal_timeline_weeks" integer      NULL,
    "activity_level"      varchar(50)  NOT NULL DEFAULT '',
    "injuries_limitations" text        NOT NULL DEFAULT '',
    "medical_conditions"  text         NOT NULL DEFAULT '',
    "medications"         text         NOT NULL DEFAULT '',
    "sleep_hours"         float        NULL,
    "stress_level"        varchar(20)  NOT NULL DEFAULT '',
    "dietary_preference"  varchar(50)  NOT NULL DEFAULT '',
    "food_allergies"      text         NOT NULL DEFAULT '',
    "disliked_foods"      text         NOT NULL DEFAULT '',
    "member_id"           bigint       NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS "members_workoutlog" (
    "id"               bigserial    PRIMARY KEY,
    "date"             date         NOT NULL DEFAULT now(),
    "workout_type"     varchar(50)  NOT NULL DEFAULT '',
    "duration_minutes" integer      NOT NULL DEFAULT 0,
    "notes"            text         NOT NULL DEFAULT '',
    "calories_burned"  integer      NULL,
    "member_id"        bigint       NOT NULL
);

CREATE TABLE IF NOT EXISTS "members_progressphoto" (
    "id"          bigserial   PRIMARY KEY,
    "photo"       varchar(100) NOT NULL,
    "taken_at"    date         NOT NULL DEFAULT now(),
    "notes"       text         NOT NULL DEFAULT '',
    "member_id"   bigint       NOT NULL
);

CREATE TABLE IF NOT EXISTS "members_bodymetric" (
    "id"             bigserial    PRIMARY KEY,
    "recorded_at"    date         NOT NULL DEFAULT now(),
    "weight_kg"      float        NULL,
    "body_fat_pct"   float        NULL,
    "muscle_mass_kg" float        NULL,
    "notes"          text         NOT NULL DEFAULT '',
    "member_id"      bigint       NOT NULL
);
"""

class Migration(migrations.Migration):
    dependencies = [
        ('members', '0003_memberprofile_fcm_token'),
        ('core', '0002_ensure_tables'),
    ]
    operations = [migrations.RunSQL(SQL, reverse_sql='SELECT 1;')]

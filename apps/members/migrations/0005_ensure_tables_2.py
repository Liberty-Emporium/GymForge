"""Repair migration — ensures remaining members tables exist (NutritionRecommendation etc)."""
from django.db import migrations

SQL = """
CREATE TABLE IF NOT EXISTS "members_nutritionrecommendation" (
    "id"                      bigserial    PRIMARY KEY,
    "generated_at"            timestamptz  NOT NULL DEFAULT now(),
    "daily_calories"          integer      NULL,
    "protein_g"               integer      NULL,
    "carbs_g"                 integer      NULL,
    "fat_g"                   integer      NULL,
    "meal_plan"               jsonb        NOT NULL DEFAULT '{}',
    "nutritionist_reviewed"   boolean      NOT NULL DEFAULT false,
    "nutritionist_notes"      text         NOT NULL DEFAULT '',
    "member_id"               bigint       NOT NULL
);

CREATE TABLE IF NOT EXISTS "members_supplementrecommendation" (
    "id"                   bigserial    PRIMARY KEY,
    "generated_at"         timestamptz  NOT NULL DEFAULT now(),
    "supplement_name"      varchar(200) NOT NULL,
    "reason"               text         NOT NULL DEFAULT '',
    "suggested_dosage"     varchar(100) NOT NULL DEFAULT '',
    "best_time_to_take"    varchar(100) NOT NULL DEFAULT '',
    "member_already_takes" boolean      NOT NULL DEFAULT false,
    "professional_override" text        NOT NULL DEFAULT '',
    "member_id"            bigint       NOT NULL,
    "override_by_id"       bigint       NULL
);

CREATE TABLE IF NOT EXISTS "members_nutritionplan" (
    "id"          bigserial    PRIMARY KEY,
    "title"       varchar(200) NOT NULL DEFAULT '',
    "plan_data"   jsonb        NOT NULL DEFAULT '{}',
    "created_at"  timestamptz  NOT NULL DEFAULT now(),
    "is_active"   boolean      NOT NULL DEFAULT true,
    "member_id"   bigint       NOT NULL,
    "created_by_id" bigint     NULL
);
"""

class Migration(migrations.Migration):
    dependencies = [('members', '0004_ensure_tables')]
    operations = [migrations.RunSQL(SQL, reverse_sql='SELECT 1;')]

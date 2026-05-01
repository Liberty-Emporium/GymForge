"""Repair migration — ensures community tables exist on Railway Postgres."""
from django.db import migrations

SQL = """
CREATE TABLE IF NOT EXISTS "community_gymchallenge" (
    "id"               bigserial    PRIMARY KEY,
    "title"            varchar(200) NOT NULL,
    "description"      text         NOT NULL DEFAULT '',
    "challenge_type"   varchar(20)  NOT NULL DEFAULT 'workouts',
    "status"           varchar(20)  NOT NULL DEFAULT 'upcoming',
    "target_value"     integer      NOT NULL DEFAULT 0,
    "unit"             varchar(50)  NOT NULL DEFAULT 'workouts',
    "start_date"       date         NOT NULL,
    "end_date"         date         NOT NULL,
    "banner_image"     varchar(100) NOT NULL DEFAULT '',
    "prize_description" text        NOT NULL DEFAULT '',
    "created_at"       timestamptz  NOT NULL DEFAULT now(),
    "created_by_id"    bigint       NULL
);

CREATE TABLE IF NOT EXISTS "community_communitypost" (
    "id"          bigserial   PRIMARY KEY,
    "post_type"   varchar(20) NOT NULL DEFAULT 'general',
    "content"     text        NOT NULL DEFAULT '',
    "image"       varchar(100) NOT NULL DEFAULT '',
    "is_pinned"   boolean     NOT NULL DEFAULT false,
    "is_visible"  boolean     NOT NULL DEFAULT true,
    "created_at"  timestamptz NOT NULL DEFAULT now(),
    "updated_at"  timestamptz NOT NULL DEFAULT now(),
    "author_id"   bigint      NOT NULL
);

CREATE TABLE IF NOT EXISTS "community_challengeentry" (
    "id"             bigserial   PRIMARY KEY,
    "current_value"  integer     NOT NULL DEFAULT 0,
    "is_completed"   boolean     NOT NULL DEFAULT false,
    "completed_at"   timestamptz NULL,
    "joined_at"      timestamptz NOT NULL DEFAULT now(),
    "last_updated"   timestamptz NOT NULL DEFAULT now(),
    "challenge_id"   bigint      NOT NULL REFERENCES "community_gymchallenge"("id") ON DELETE CASCADE,
    "member_id"      bigint      NOT NULL
);

CREATE TABLE IF NOT EXISTS "community_postlike" (
    "id"       bigserial   PRIMARY KEY,
    "liked_at" timestamptz NOT NULL DEFAULT now(),
    "post_id"  bigint      NOT NULL REFERENCES "community_communitypost"("id") ON DELETE CASCADE,
    "user_id"  bigint      NOT NULL
);

CREATE TABLE IF NOT EXISTS "community_postcomment" (
    "id"         bigserial    PRIMARY KEY,
    "content"    text         NOT NULL DEFAULT '',
    "created_at" timestamptz  NOT NULL DEFAULT now(),
    "post_id"    bigint       NOT NULL REFERENCES "community_communitypost"("id") ON DELETE CASCADE,
    "author_id"  bigint       NOT NULL
);
"""

class Migration(migrations.Migration):
    dependencies = [('community', '0001_initial')]
    operations = [migrations.RunSQL(SQL, reverse_sql='SELECT 1;')]

# Retention Automation — Design Spec
**Step 44 · GymForge v2**
Date: 2026-03-26

---

## Overview

Three Celery beat tasks in `apps/members/tasks.py` automate member retention:
daily inactivity detection with re-engagement messaging, birthday rewards, and
14-day gym trial lifecycle management. A shared helper `send_reengagement_message`
handles push + email delivery. Two schema changes support the feature.

---

## 1. Schema Changes

### 1a. `MemberProfile.fcm_token`

**File:** `apps/members/models.py`
**Migration:** `apps/members/migrations/0002_memberprofile_fcm_token.py`

```python
fcm_token = models.CharField(max_length=255, blank=True)
```

Stores the Firebase Cloud Messaging registration token for the member's mobile
device. Set by the mobile app when registering or refreshing. Blank means no
push device registered — push is skipped silently, email still sent.

### 1b. `GymTenant.trial_emails_sent`

**File:** `apps/tenants/models.py`
**Migration:** `apps/tenants/migrations/0002_gymtenant_trial_emails_sent.py`

```python
trial_emails_sent = models.JSONField(default=list)
```

A list of integer day numbers for which the trial email has already been sent
(e.g., `[0, 3, 7]`). Used by `process_trial_statuses` to prevent re-sending
on task retry or if a day is missed. Appended to atomically on each successful
send; never removed.

---

## 2. `apps/members/tasks.py` — New File

### `send_reengagement_message(member, days_inactive)`

Plain helper function (not a Celery task). Called by `check_member_retention`.

**Inputs:**
- `member` — `MemberProfile` instance
- `days_inactive` — `int`

**Flow:**
1. Build personalised message: `f"Hi {member.user.first_name}, we miss you! It's been {days_inactive} days since your last visit. Come back and keep up your progress!"`
2. **Push** (if `member.fcm_token` is non-blank):
   ```python
   from pyfcm import FCMNotification
   push_service = FCMNotification(api_key=settings.FCM_SERVER_KEY)
   push_service.notify_single_device(
       registration_id=member.fcm_token,
       message_title='We miss you!',
       message_body=message,
   )
   ```
3. **Email** (always):
   ```python
   send_mail(
       subject='We miss you at the gym!',
       message=message,
       from_email=settings.DEFAULT_FROM_EMAIL,
       recipient_list=[member.user.email],
       fail_silently=True,
   )
   ```
4. All exceptions caught and logged — never raises.

---

### `check_member_retention`

```python
@shared_task
def check_member_retention():
```

**Schedule:** Daily at 09:00 UTC.

**Flow:**
1. Import `GymTenant`, `schema_context`, `MemberProfile`, `MemberAIAlert` inside function. (`CheckIn` is not imported directly — `member.checkins` is a reverse relation.)
2. Iterate `GymTenant.objects.filter(subscription_status__in=['trial', 'active'])`.
3. For each tenant, wrap in `schema_context(tenant.schema_name)`.
4. Query active members:
   ```python
   members = MemberProfile.objects.filter(
       memberships__status='active'
   ).select_related('user').distinct()
   ```
5. For each member:
   - Get last activity:
     ```python
     last_checkin = member.checkins.order_by('-checked_in_at').first()
     last_activity = last_checkin.checked_in_at.date() if last_checkin else member.join_date
     ```
   - `days_inactive = (today - last_activity).days`
   - If `days_inactive >= 30`:
     - Create `MemberAIAlert` if no unresolved inactivity alert exists:
       ```python
       MemberAIAlert.objects.get_or_create(
           member=member,
           alert_type='inactivity',
           is_resolved=False,
           defaults={'message': f'Member inactive for {days_inactive} days.'},
       )
       ```
     - Call `send_reengagement_message(member, days_inactive)`
   - Elif `days_inactive >= 14`:
     - Call `send_reengagement_message(member, days_inactive)`
6. Per-member `except Exception` → `logger.exception(...)`, continue loop.
7. Per-tenant `except Exception` → `logger.exception(...)`, continue to next tenant.

---

### `send_birthday_messages`

```python
@shared_task
def send_birthday_messages():
```

**Schedule:** Daily at 08:00 UTC.

**Flow:**
1. Import `GymTenant`, `schema_context`, `MemberProfile` inside function.
2. Compute `today = timezone.now().date()`.
3. Iterate active tenants via `schema_context`.
4. Query:
   ```python
   members = MemberProfile.objects.filter(
       date_of_birth__month=today.month,
       date_of_birth__day=today.day,
   ).select_related('user')
   ```
5. For each member:
   - `points = award_loyalty_points(member, 'birthday', description='Happy Birthday!')`
   - Send push (if `member.fcm_token`): title `'Happy Birthday! 🎂'`, body `f'Happy Birthday {member.user.first_name}! Enjoy your {points} bonus loyalty points.'`
   - Send email: subject `f'Happy Birthday from {tenant.gym_name}!'`, body `f'Happy Birthday {member.user.first_name}! We have awarded you {points} bonus loyalty points. See you at the gym!'`
6. Per-member `except Exception` → log, continue.
7. Per-tenant `except Exception` → log, continue.

**Note:** `award_loyalty_points` enforces `daily_cap` via `LoyaltyRule`, so duplicate birthday points are automatically prevented.

---

### `process_trial_statuses`

```python
@shared_task
def process_trial_statuses():
```

**Schedule:** Daily at 00:00 UTC (midnight).

**Runs in public schema** — `GymTenant` is a public model; no `schema_context` loop.

**Trial email days:** `{0, 3, 7, 10, 13}` — welcome/nudge sequence. Day 14 = trial ended.

**Flow:**
1. Import `GymTenant` inside function.
2. `today = timezone.now().date()`
3. Iterate `GymTenant.objects.filter(trial_active=True)`.
4. For each tenant:
   - `elapsed = (today - tenant.trial_start_date.date()).days`
   - **Day 14+ and still active:**
     ```python
     if elapsed >= 14:
         tenant.trial_active = False
         tenant.subscription_status = 'suspended'
         if 14 not in tenant.trial_emails_sent:
             _send_trial_email(tenant, 'day14_ended')
             tenant.trial_emails_sent = tenant.trial_emails_sent + [14]
         tenant.save(update_fields=['trial_active', 'subscription_status', 'trial_emails_sent'])
     ```
   - **Nudge days (0, 3, 7, 10, 13):**
     ```python
     elif elapsed in {0, 3, 7, 10, 13} and elapsed not in tenant.trial_emails_sent:
         _send_trial_email(tenant, f'day{elapsed}')
         tenant.trial_emails_sent = tenant.trial_emails_sent + [elapsed]
         tenant.save(update_fields=['trial_emails_sent'])
     ```
5. Per-tenant `except Exception` → log, continue.

### `_send_trial_email(tenant, template_key)`

Private helper called by `process_trial_statuses`.

Sends email to `tenant.owner_email`. Subject and body vary by `template_key`:

| `template_key` | Subject | Body summary |
|---|---|---|
| `day0` | Welcome to GymForge! Your trial starts now. | Welcome + feature highlights |
| `day3` | How's your first week going? | Check-in + tips |
| `day7` | 7 days in — here's what's working | Halfway milestone |
| `day10` | 4 days left on your trial | Gentle urgency |
| `day13` | Tomorrow is your last trial day | Strong CTA to subscribe |
| `day14_ended` | Your GymForge trial has ended | Subscription link + what they'll lose |

Uses `send_mail(..., fail_silently=True)`.

---

## 3. `config/settings/base.py` — Celery Beat Additions

Add to `CELERY_BEAT_SCHEDULE`:

```python
'check-member-retention-daily': {
    'task': 'apps.members.tasks.check_member_retention',
    'schedule': crontab(hour=9, minute=0),
},
'send-birthday-messages-daily': {
    'task': 'apps.members.tasks.send_birthday_messages',
    'schedule': crontab(hour=8, minute=0),
},
'process-trial-statuses-daily': {
    'task': 'apps.members.tasks.process_trial_statuses',
    'schedule': crontab(hour=0, minute=0),
},
```

---

## 4. Files Changed / Created

| File | Action |
|------|--------|
| `apps/members/tasks.py` | Create |
| `apps/members/models.py` | Add `fcm_token` to `MemberProfile` |
| `apps/members/migrations/0002_memberprofile_fcm_token.py` | Create (via makemigrations) |
| `apps/tenants/models.py` | Add `trial_emails_sent` to `GymTenant` |
| `apps/tenants/migrations/0002_gymtenant_trial_emails_sent.py` | Create (via makemigrations) |
| `config/settings/base.py` | Add 3 Celery beat entries |

---

## 5. Fault Tolerance

All three tasks follow the same pattern:
- Per-member/per-tenant `except Exception` with `logger.exception(...)` — one failure never stops the loop
- Push failures are swallowed within `send_reengagement_message` — email still attempted
- `fail_silently=True` on all `send_mail` calls
- `trial_emails_sent` is idempotent — task can be retried without double-sending

---

## 6. Out of Scope

- Owner-facing UI for retention alerts (surfaces via existing trainer/owner portals through `MemberAIAlert`)
- FCM token registration endpoint (mobile app responsibility, Step 45+)
- Timezone-aware scheduling per gym (all UTC for now)
- Unsubscribe / opt-out from retention emails

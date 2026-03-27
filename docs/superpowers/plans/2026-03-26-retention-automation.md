# Retention Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three Celery beat tasks (`check_member_retention`, `send_birthday_messages`, `process_trial_statuses`) plus a shared helper (`send_reengagement_message`) to automate member retention, birthday rewards, and trial lifecycle emails.

**Architecture:** All tasks live in `apps/members/tasks.py` (new file). Two schema fields are added first: `MemberProfile.fcm_token` (Firebase push token) and `GymTenant.trial_emails_sent` (idempotency list). Model imports are at module level — same pattern as `apps/billing/tasks.py` — so test patches via `patch('apps.members.tasks.X')` resolve correctly. The public-schema `process_trial_statuses` task iterates `GymTenant` directly without a `schema_context` loop.

**Tech Stack:** Django · Celery (`@shared_task`) · pyfcm (Firebase Cloud Messaging) · SendGrid via django-anymail · django-tenants (`schema_context`)

---

## File Map

| File | Action |
|------|--------|
| `apps/members/models.py` | Add `fcm_token` CharField after `pin_hash` |
| `apps/members/migrations/0003_memberprofile_fcm_token.py` | Create |
| `apps/tenants/models.py` | Add `trial_emails_sent` JSONField after `trial_active` |
| `apps/tenants/migrations/0002_gymtenant_trial_emails_sent.py` | Create |
| `apps/members/tasks.py` | Create — 4 functions built across Tasks 3–6 |
| `apps/members/tests.py` | Create — unit tests (no DB required), built across Tasks 3–6 |
| `config/settings/base.py` | Add 3 entries to `CELERY_BEAT_SCHEDULE` |

---

## Task 1: Schema — MemberProfile.fcm_token

**Files:**
- Modify: `apps/members/models.py`
- Create: `apps/members/migrations/0003_memberprofile_fcm_token.py`

- [ ] **Step 1: Add field to model**

In `apps/members/models.py`, after line 106 (`pin_hash = models.CharField(max_length=128, blank=True)`), insert:

```python
    # Firebase Cloud Messaging registration token for push notifications (Step 44)
    fcm_token = models.CharField(max_length=255, blank=True)
```

- [ ] **Step 2: Write migration**

Create `apps/members/migrations/0003_memberprofile_fcm_token.py`:

```python
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('members', '0002_add_pin_hash_to_member_profile'),
    ]

    operations = [
        migrations.AddField(
            model_name='memberprofile',
            name='fcm_token',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
```

- [ ] **Step 3: Commit**

```bash
git add apps/members/models.py apps/members/migrations/0003_memberprofile_fcm_token.py
git commit -m "feat: add fcm_token to MemberProfile for push notifications"
```

---

## Task 2: Schema — GymTenant.trial_emails_sent

**Files:**
- Modify: `apps/tenants/models.py`
- Create: `apps/tenants/migrations/0002_gymtenant_trial_emails_sent.py`

- [ ] **Step 1: Add field to model**

In `apps/tenants/models.py`, after line 47 (`trial_active = models.BooleanField(default=True)`), insert:

```python
    # Day numbers for which trial emails have already been sent — prevents re-sends on retry.
    # e.g. [0, 3, 7] — appended on each successful send; never removed.
    trial_emails_sent = models.JSONField(default=list)
```

- [ ] **Step 2: Write migration**

Create `apps/tenants/migrations/0002_gymtenant_trial_emails_sent.py`:

```python
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='gymtenant',
            name='trial_emails_sent',
            field=models.JSONField(default=list),
        ),
    ]
```

- [ ] **Step 3: Commit**

```bash
git add apps/tenants/models.py apps/tenants/migrations/0002_gymtenant_trial_emails_sent.py
git commit -m "feat: add trial_emails_sent to GymTenant for idempotent trial email tracking"
```

---

## Task 3: send_reengagement_message helper

**Files:**
- Create: `apps/members/tasks.py`
- Create: `apps/members/tests.py`

- [ ] **Step 1: Write failing tests**

Create `apps/members/tests.py`:

```python
"""
Unit tests for apps/members/tasks.py.

All model access is mocked — these tests run without a tenant DB context.
Uses SimpleTestCase so Django doesn't set up a database at all.
"""
import datetime
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

def _make_member(fcm_token='', days_inactive=20):
    """Return a MagicMock MemberProfile with checkin history set to days_inactive ago."""
    user = MagicMock()
    user.first_name = 'Alice'
    user.email = 'alice@example.com'

    today = timezone.now().date()
    checkin = MagicMock()
    checkin.checked_in_at.date.return_value = today - datetime.timedelta(days=days_inactive)

    member = MagicMock()
    member.pk = 1
    member.user = user
    member.fcm_token = fcm_token
    member.join_date = today - datetime.timedelta(days=days_inactive)
    member.checkins.order_by.return_value.first.return_value = checkin
    return member


def _make_tenant(
    subscription_status='active',
    trial_active=True,
    trial_days_ago=0,
    trial_emails_sent=None,
):
    today = timezone.now().date()
    tenant = MagicMock()
    tenant.schema_name = 'gym_test'
    tenant.gym_name = 'Test Gym'
    tenant.owner_email = 'owner@testgym.com'
    tenant.subscription_status = subscription_status
    tenant.trial_active = trial_active
    tenant.trial_start_date.date.return_value = today - datetime.timedelta(days=trial_days_ago)
    tenant.trial_emails_sent = trial_emails_sent if trial_emails_sent is not None else []
    return tenant


# ---------------------------------------------------------------------------
# Tests: send_reengagement_message
# ---------------------------------------------------------------------------

class SendReengagementMessageTest(SimpleTestCase):

    def test_sends_push_when_fcm_token_non_blank(self):
        """Push is sent when member has a non-blank fcm_token."""
        member = _make_member(fcm_token='device_tok_abc')
        with patch('apps.members.tasks.FCMNotification') as MockFCM, \
             patch('apps.members.tasks.send_mail'):
            from apps.members.tasks import send_reengagement_message
            send_reengagement_message(member, 20)
        MockFCM.assert_called_once()
        kwargs = MockFCM.return_value.notify_single_device.call_args[1]
        assert kwargs['registration_id'] == 'device_tok_abc'
        assert kwargs['message_title'] == 'We miss you!'

    def test_skips_push_when_no_fcm_token(self):
        """Push is NOT sent when fcm_token is blank; email is still sent."""
        member = _make_member(fcm_token='')
        with patch('apps.members.tasks.FCMNotification') as MockFCM, \
             patch('apps.members.tasks.send_mail') as mock_mail:
            from apps.members.tasks import send_reengagement_message
            send_reengagement_message(member, 20)
        MockFCM.assert_not_called()
        mock_mail.assert_called_once()

    def test_email_contains_days_inactive_count_and_correct_subject(self):
        """Email body includes the days count; subject is 'We miss you at the gym!'."""
        member = _make_member()
        with patch('apps.members.tasks.FCMNotification'), \
             patch('apps.members.tasks.send_mail') as mock_mail:
            from apps.members.tasks import send_reengagement_message
            send_reengagement_message(member, 42)
        kwargs = mock_mail.call_args[1]
        assert '42' in kwargs['message']
        assert kwargs['subject'] == 'We miss you at the gym!'
        assert kwargs['recipient_list'] == ['alice@example.com']

    def test_push_exception_does_not_prevent_email(self):
        """If push raises, email is still attempted — function never raises."""
        member = _make_member(fcm_token='tok')
        with patch('apps.members.tasks.FCMNotification') as MockFCM, \
             patch('apps.members.tasks.send_mail') as mock_mail:
            MockFCM.return_value.notify_single_device.side_effect = Exception('FCM down')
            from apps.members.tasks import send_reengagement_message
            send_reengagement_message(member, 20)  # must not raise
        mock_mail.assert_called_once()
```

- [ ] **Step 2: Run tests — expect import error**

```bash
cd "/home/mingo/Documents/Finished APPs for Demos/GymForge"
python -m pytest apps/members/tests.py::SendReengagementMessageTest -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError` or `ImportError` — `apps.members.tasks` does not exist yet.

- [ ] **Step 3: Create tasks.py with helper**

Create `apps/members/tasks.py`:

```python
"""
Retention Celery tasks — Step 44 GymForge v2.

send_reengagement_message  — push + email helper for inactive members.
check_member_retention     — daily 09:00 UTC; 14/30-day inactivity alerts.
send_birthday_messages     — daily 08:00 UTC; birthday loyalty points + messages.
process_trial_statuses     — daily 00:00 UTC; trial nudge emails + day-14 suspension.

Import note: models imported at module level (rather than deferred inside functions)
so that test patches via patch('apps.members.tasks.X') resolve correctly. This
follows the same pattern established in apps/billing/tasks.py.
"""
import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django_tenants.utils import schema_context
from pyfcm import FCMNotification

from apps.ai_coach.models import MemberAIAlert
from apps.loyalty.utils import award_loyalty_points
from apps.members.models import MemberProfile
from apps.tenants.models import GymTenant

logger = logging.getLogger(__name__)


def send_reengagement_message(member, days_inactive):
    """Send push notification + email to a member who has been inactive."""
    message = (
        f"Hi {member.user.first_name}, we miss you! It's been {days_inactive} days "
        f"since your last visit. Come back and keep up your progress!"
    )
    try:
        if member.fcm_token:
            push_service = FCMNotification(api_key=settings.FCM_SERVER_KEY)
            push_service.notify_single_device(
                registration_id=member.fcm_token,
                message_title='We miss you!',
                message_body=message,
            )
    except Exception:
        logger.exception('Push notification failed for member %s', member.pk)
    try:
        send_mail(
            subject='We miss you at the gym!',
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[member.user.email],
            fail_silently=True,
        )
    except Exception:
        logger.exception('Re-engagement email failed for member %s', member.pk)
```

- [ ] **Step 4: Run tests — expect green**

```bash
python -m pytest apps/members/tests.py::SendReengagementMessageTest -v
```

Expected: 4 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add apps/members/tasks.py apps/members/tests.py
git commit -m "feat: add send_reengagement_message helper with tests"
```

---

## Task 4: check_member_retention task

**Files:**
- Modify: `apps/members/tasks.py` (append `check_member_retention`)
- Modify: `apps/members/tests.py` (append `CheckMemberRetentionTest`)

- [ ] **Step 1: Write failing tests**

Append to `apps/members/tests.py`:

```python
# ---------------------------------------------------------------------------
# Tests: check_member_retention
# ---------------------------------------------------------------------------

class CheckMemberRetentionTest(SimpleTestCase):

    def _run_task(self, members, tenants=None):
        """Run check_member_retention with the given members/tenants fully mocked."""
        if tenants is None:
            tenants = [_make_tenant()]
        with patch('apps.members.tasks.GymTenant') as MockTenant, \
             patch('apps.members.tasks.schema_context'), \
             patch('apps.members.tasks.MemberProfile') as MockMember, \
             patch('apps.members.tasks.MemberAIAlert') as MockAlert, \
             patch('apps.members.tasks.send_reengagement_message') as mock_send:
            MockTenant.objects.filter.return_value = tenants
            (MockMember.objects.filter.return_value
             .select_related.return_value.distinct.return_value) = members
            from apps.members.tasks import check_member_retention
            check_member_retention()
        return mock_send, MockAlert

    def test_30_day_inactive_creates_alert_and_sends_message(self):
        """Member inactive 30+ days: MemberAIAlert created + re-engagement message sent."""
        member = _make_member(days_inactive=30)
        mock_send, MockAlert = self._run_task([member])
        MockAlert.objects.get_or_create.assert_called_once_with(
            member=member,
            alert_type='inactivity',
            is_resolved=False,
            defaults={'message': 'Member inactive for 30 days.'},
        )
        mock_send.assert_called_once_with(member, 30)

    def test_14_day_inactive_sends_message_but_no_alert(self):
        """Member inactive 14–29 days: re-engagement message only, no MemberAIAlert."""
        member = _make_member(days_inactive=14)
        mock_send, MockAlert = self._run_task([member])
        MockAlert.objects.get_or_create.assert_not_called()
        mock_send.assert_called_once_with(member, 14)

    def test_13_day_inactive_does_nothing(self):
        """Member inactive fewer than 14 days: no alert, no message."""
        member = _make_member(days_inactive=13)
        mock_send, MockAlert = self._run_task([member])
        mock_send.assert_not_called()
        MockAlert.objects.get_or_create.assert_not_called()

    def test_continues_to_next_member_on_exception(self):
        """Per-member exception is caught; subsequent members are still processed."""
        member1 = _make_member(days_inactive=30)
        member1.checkins.order_by.side_effect = Exception('DB error')
        member2 = _make_member(days_inactive=30)
        member2.pk = 2
        mock_send, _ = self._run_task([member1, member2])
        mock_send.assert_called_once_with(member2, 30)

    def test_continues_to_next_tenant_on_exception(self):
        """Per-tenant exception is caught; subsequent tenants are still processed."""
        tenant1 = _make_tenant()
        tenant2 = _make_tenant()
        member = _make_member(days_inactive=30)
        call_count = {'n': 0}

        def fake_schema_ctx(schema_name):
            call_count['n'] += 1
            if call_count['n'] == 1:
                raise Exception('schema error')
            return MagicMock()

        with patch('apps.members.tasks.GymTenant') as MockTenant, \
             patch('apps.members.tasks.schema_context', side_effect=fake_schema_ctx), \
             patch('apps.members.tasks.MemberProfile') as MockMember, \
             patch('apps.members.tasks.MemberAIAlert'), \
             patch('apps.members.tasks.send_reengagement_message') as mock_send:
            MockTenant.objects.filter.return_value = [tenant1, tenant2]
            (MockMember.objects.filter.return_value
             .select_related.return_value.distinct.return_value) = [member]
            from apps.members.tasks import check_member_retention
            check_member_retention()

        mock_send.assert_called_once_with(member, 30)
```

- [ ] **Step 2: Run tests — expect failure**

```bash
python -m pytest apps/members/tests.py::CheckMemberRetentionTest -v
```

Expected: 5 tests FAILED — `check_member_retention` is not yet defined.

- [ ] **Step 3: Append check_member_retention to tasks.py**

Append to `apps/members/tasks.py`:

```python
@shared_task
def check_member_retention():
    """Scan all active tenants for inactive members; send re-engagement messages."""
    today = timezone.now().date()
    for tenant in GymTenant.objects.filter(subscription_status__in=['trial', 'active']):
        try:
            with schema_context(tenant.schema_name):
                members = (
                    MemberProfile.objects
                    .filter(memberships__status='active')
                    .select_related('user')
                    .distinct()
                )
                for member in members:
                    try:
                        last_checkin = member.checkins.order_by('-checked_in_at').first()
                        last_activity = (
                            last_checkin.checked_in_at.date()
                            if last_checkin
                            else member.join_date
                        )
                        days_inactive = (today - last_activity).days
                        if days_inactive >= 30:
                            MemberAIAlert.objects.get_or_create(
                                member=member,
                                alert_type='inactivity',
                                is_resolved=False,
                                defaults={
                                    'message': f'Member inactive for {days_inactive} days.'
                                },
                            )
                            send_reengagement_message(member, days_inactive)
                        elif days_inactive >= 14:
                            send_reengagement_message(member, days_inactive)
                    except Exception:
                        logger.exception(
                            'check_member_retention failed for member %s', member.pk
                        )
        except Exception:
            logger.exception(
                'check_member_retention failed for tenant %s', tenant.schema_name
            )
```

- [ ] **Step 4: Run tests — expect green**

```bash
python -m pytest apps/members/tests.py::CheckMemberRetentionTest -v
```

Expected: 5 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add apps/members/tasks.py apps/members/tests.py
git commit -m "feat: add check_member_retention Celery task with tests"
```

---

## Task 5: send_birthday_messages task

**Files:**
- Modify: `apps/members/tasks.py` (append `send_birthday_messages`)
- Modify: `apps/members/tests.py` (append `SendBirthdayMessagesTest`)

- [ ] **Step 1: Write failing tests**

Append to `apps/members/tests.py`:

```python
# ---------------------------------------------------------------------------
# Tests: send_birthday_messages
# ---------------------------------------------------------------------------

class SendBirthdayMessagesTest(SimpleTestCase):

    def _run_task(self, members, tenants=None):
        if tenants is None:
            tenants = [_make_tenant()]
        with patch('apps.members.tasks.GymTenant') as MockTenant, \
             patch('apps.members.tasks.schema_context'), \
             patch('apps.members.tasks.MemberProfile') as MockMember, \
             patch('apps.members.tasks.award_loyalty_points', return_value=100) as mock_award, \
             patch('apps.members.tasks.FCMNotification') as MockFCM, \
             patch('apps.members.tasks.send_mail') as mock_mail:
            MockTenant.objects.filter.return_value = tenants
            (MockMember.objects.filter.return_value
             .select_related.return_value) = members
            from apps.members.tasks import send_birthday_messages
            send_birthday_messages()
        return mock_award, MockFCM, mock_mail

    def test_awards_birthday_loyalty_points(self):
        """Loyalty points awarded with action='birthday' for each birthday member."""
        member = _make_member()
        mock_award, _, _ = self._run_task([member])
        mock_award.assert_called_once_with(member, 'birthday', description='Happy Birthday!')

    def test_sends_push_when_fcm_token_set(self):
        """Push notification sent when member has an fcm_token; body includes points count."""
        member = _make_member(fcm_token='tok_xyz')
        _, MockFCM, _ = self._run_task([member])
        MockFCM.return_value.notify_single_device.assert_called_once()
        kwargs = MockFCM.return_value.notify_single_device.call_args[1]
        assert kwargs['message_title'] == 'Happy Birthday! 🎂'
        assert '100' in kwargs['message_body']

    def test_skips_push_when_no_fcm_token(self):
        """No push when fcm_token is blank."""
        member = _make_member(fcm_token='')
        _, MockFCM, _ = self._run_task([member])
        MockFCM.return_value.notify_single_device.assert_not_called()

    def test_birthday_email_contains_gym_name_and_points(self):
        """Email subject includes gym name; body includes points awarded."""
        member = _make_member()
        _, _, mock_mail = self._run_task([member])
        mock_mail.assert_called_once()
        assert 'Test Gym' in mock_mail.call_args[1]['subject']
        assert '100' in mock_mail.call_args[1]['message']

    def test_continues_on_member_exception(self):
        """Per-member exception is caught; other members are still processed."""
        member1 = _make_member()
        member2 = _make_member()
        member2.pk = 2
        with patch('apps.members.tasks.GymTenant') as MockTenant, \
             patch('apps.members.tasks.schema_context'), \
             patch('apps.members.tasks.MemberProfile') as MockMember, \
             patch('apps.members.tasks.award_loyalty_points') as mock_award, \
             patch('apps.members.tasks.FCMNotification'), \
             patch('apps.members.tasks.send_mail'):
            MockTenant.objects.filter.return_value = [_make_tenant()]
            (MockMember.objects.filter.return_value
             .select_related.return_value) = [member1, member2]
            mock_award.side_effect = [Exception('db err'), 50]
            from apps.members.tasks import send_birthday_messages
            send_birthday_messages()  # must not raise
        assert mock_award.call_count == 2
```

- [ ] **Step 2: Run tests — expect failure**

```bash
python -m pytest apps/members/tests.py::SendBirthdayMessagesTest -v
```

Expected: 5 tests FAILED — `send_birthday_messages` is not yet defined.

- [ ] **Step 3: Append send_birthday_messages to tasks.py**

Append to `apps/members/tasks.py`:

```python
@shared_task
def send_birthday_messages():
    """Award birthday loyalty points and send push + email to members with today's birthday."""
    today = timezone.now().date()
    for tenant in GymTenant.objects.filter(subscription_status__in=['trial', 'active']):
        try:
            with schema_context(tenant.schema_name):
                members = (
                    MemberProfile.objects
                    .filter(
                        date_of_birth__month=today.month,
                        date_of_birth__day=today.day,
                    )
                    .select_related('user')
                )
                for member in members:
                    try:
                        points = award_loyalty_points(
                            member, 'birthday', description='Happy Birthday!'
                        )
                        if member.fcm_token:
                            push_service = FCMNotification(api_key=settings.FCM_SERVER_KEY)
                            push_service.notify_single_device(
                                registration_id=member.fcm_token,
                                message_title='Happy Birthday! 🎂',
                                message_body=(
                                    f'Happy Birthday {member.user.first_name}! '
                                    f'Enjoy your {points} bonus loyalty points.'
                                ),
                            )
                        send_mail(
                            subject=f'Happy Birthday from {tenant.gym_name}!',
                            message=(
                                f'Happy Birthday {member.user.first_name}! '
                                f'We have awarded you {points} bonus loyalty points. '
                                f'See you at the gym!'
                            ),
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[member.user.email],
                            fail_silently=True,
                        )
                    except Exception:
                        logger.exception(
                            'Birthday message failed for member %s', member.pk
                        )
        except Exception:
            logger.exception(
                'send_birthday_messages failed for tenant %s', tenant.schema_name
            )
```

- [ ] **Step 4: Run tests — expect green**

```bash
python -m pytest apps/members/tests.py::SendBirthdayMessagesTest -v
```

Expected: 5 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add apps/members/tasks.py apps/members/tests.py
git commit -m "feat: add send_birthday_messages Celery task with tests"
```

---

## Task 6: process_trial_statuses + _send_trial_email

**Files:**
- Modify: `apps/members/tasks.py` (append `_send_trial_email`, `process_trial_statuses`)
- Modify: `apps/members/tests.py` (append `ProcessTrialStatusesTest`)

- [ ] **Step 1: Write failing tests**

Append to `apps/members/tests.py`:

```python
# ---------------------------------------------------------------------------
# Tests: process_trial_statuses
# ---------------------------------------------------------------------------

class ProcessTrialStatusesTest(SimpleTestCase):

    def _run_task(self, tenants):
        with patch('apps.members.tasks.GymTenant') as MockTenant, \
             patch('apps.members.tasks._send_trial_email') as mock_email:
            MockTenant.objects.filter.return_value = tenants
            from apps.members.tasks import process_trial_statuses
            process_trial_statuses()
        return mock_email

    def test_day14_sets_trial_active_false_and_status_suspended(self):
        """Day 14+: trial_active=False and subscription_status='suspended' are saved."""
        tenant = _make_tenant(trial_active=True, trial_days_ago=14)
        self._run_task([tenant])
        assert tenant.trial_active is False
        assert tenant.subscription_status == 'suspended'
        tenant.save.assert_called_once()
        update_fields = tenant.save.call_args[1]['update_fields']
        assert 'trial_active' in update_fields
        assert 'subscription_status' in update_fields

    def test_day14_sends_ended_email_if_not_already_sent(self):
        """Day 14+: sends day14_ended email and appends 14 to trial_emails_sent."""
        tenant = _make_tenant(trial_days_ago=14, trial_emails_sent=[])
        mock_email = self._run_task([tenant])
        mock_email.assert_called_once_with(tenant, 'day14_ended')
        assert 14 in tenant.trial_emails_sent

    def test_day14_does_not_resend_if_already_sent(self):
        """Day 14+: no email when 14 is already in trial_emails_sent (idempotent)."""
        tenant = _make_tenant(trial_days_ago=14, trial_emails_sent=[14])
        mock_email = self._run_task([tenant])
        mock_email.assert_not_called()

    def test_nudge_day_sends_email_if_not_sent(self):
        """Day 7 nudge: sends day7 email and appends 7 to trial_emails_sent."""
        tenant = _make_tenant(trial_days_ago=7, trial_emails_sent=[0, 3])
        mock_email = self._run_task([tenant])
        mock_email.assert_called_once_with(tenant, 'day7')
        assert 7 in tenant.trial_emails_sent

    def test_nudge_day_skips_if_already_sent(self):
        """Day 7 nudge: no email when 7 is already in trial_emails_sent."""
        tenant = _make_tenant(trial_days_ago=7, trial_emails_sent=[0, 3, 7])
        mock_email = self._run_task([tenant])
        mock_email.assert_not_called()

    def test_non_nudge_day_does_nothing(self):
        """Day 5 (not a nudge day): no email sent, no save called."""
        tenant = _make_tenant(trial_days_ago=5, trial_emails_sent=[0, 3])
        mock_email = self._run_task([tenant])
        mock_email.assert_not_called()
        tenant.save.assert_not_called()

    def test_continues_to_next_tenant_on_exception(self):
        """Per-tenant exception is caught; other tenants are still processed."""
        tenant1 = _make_tenant(trial_days_ago=7, trial_emails_sent=[])
        tenant2 = _make_tenant(trial_days_ago=7, trial_emails_sent=[])
        with patch('apps.members.tasks.GymTenant') as MockTenant, \
             patch('apps.members.tasks._send_trial_email') as mock_email:
            MockTenant.objects.filter.return_value = [tenant1, tenant2]
            mock_email.side_effect = [Exception('send error'), None]
            from apps.members.tasks import process_trial_statuses
            process_trial_statuses()  # must not raise
        assert mock_email.call_count == 2
```

- [ ] **Step 2: Run tests — expect failure**

```bash
python -m pytest apps/members/tests.py::ProcessTrialStatusesTest -v
```

Expected: 7 tests FAILED — `process_trial_statuses` is not yet defined.

- [ ] **Step 3: Append _send_trial_email and process_trial_statuses to tasks.py**

Append to `apps/members/tasks.py`:

```python
def _send_trial_email(tenant, template_key):
    """Send a trial lifecycle email to the gym owner. Called only by process_trial_statuses."""
    subjects = {
        'day0': 'Welcome to GymForge! Your trial starts now.',
        'day3': "How's your first week going?",
        'day7': "7 days in — here's what's working",
        'day10': '4 days left on your trial',
        'day13': 'Tomorrow is your last trial day',
        'day14_ended': 'Your GymForge trial has ended',
    }
    bodies = {
        'day0': (
            f'Welcome to GymForge, {tenant.gym_name}!\n\n'
            'Your 14-day free trial has started. Key features to explore:\n'
            '- Member check-in and RFID management\n'
            '- Class scheduling and booking\n'
            '- Loyalty points and rewards\n'
            '- AI coach for member wellness\n\n'
            'Get started at your GymForge dashboard.'
        ),
        'day3': (
            f'Hi {tenant.gym_name},\n\n'
            "You're 3 days into your trial. Tips to get the most from it:\n"
            '- Add your first members and run a check-in\n'
            '- Set up a class schedule\n'
            '- Configure your membership tiers\n\n'
            'Reply to this email if you have questions.'
        ),
        'day7': (
            f'Hi {tenant.gym_name},\n\n'
            "You're halfway through your GymForge trial. Here's what's working:\n\n"
            '- Automated check-in saves 30 minutes of admin per day\n'
            '- Members love the class booking system\n'
            '- Loyalty points increase visit frequency by 20%\n\n'
            'Subscribe anytime from your dashboard.'
        ),
        'day10': (
            f'Hi {tenant.gym_name},\n\n'
            'You have 4 days left on your GymForge trial.\n\n'
            'Subscribe before your trial ends to keep all your data and continue '
            'serving your members without interruption.'
        ),
        'day13': (
            f'Hi {tenant.gym_name},\n\n'
            'Tomorrow is your last trial day.\n\n'
            'Subscribe today to keep your gym running without interruption. '
            'Your members, data, and settings are all ready to go.'
        ),
        'day14_ended': (
            f'Hi {tenant.gym_name},\n\n'
            'Your GymForge trial has ended and your account is now suspended.\n\n'
            'Subscribe to restore access. Your data is safe and will be '
            'retained for 30 days.\n\n'
            "What you'll lose access to until you subscribe:\n"
            '- Member check-in\n'
            '- Class scheduling\n'
            '- Loyalty points\n'
            '- AI coach\n\n'
            'Subscribe now to restore access immediately.'
        ),
    }
    send_mail(
        subject=subjects[template_key],
        message=bodies[template_key],
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[tenant.owner_email],
        fail_silently=True,
    )


@shared_task
def process_trial_statuses():
    """
    Run daily at midnight UTC. Sends trial nudge emails at days 0/3/7/10/13;
    suspends tenant at day 14. Operates in the public schema — no schema_context loop.
    """
    today = timezone.now().date()
    for tenant in GymTenant.objects.filter(trial_active=True):
        try:
            elapsed = (today - tenant.trial_start_date.date()).days
            if elapsed >= 14:
                tenant.trial_active = False
                tenant.subscription_status = 'suspended'
                if 14 not in tenant.trial_emails_sent:
                    _send_trial_email(tenant, 'day14_ended')
                    tenant.trial_emails_sent = tenant.trial_emails_sent + [14]
                tenant.save(
                    update_fields=['trial_active', 'subscription_status', 'trial_emails_sent']
                )
            elif elapsed in {0, 3, 7, 10, 13} and elapsed not in tenant.trial_emails_sent:
                _send_trial_email(tenant, f'day{elapsed}')
                tenant.trial_emails_sent = tenant.trial_emails_sent + [elapsed]
                tenant.save(update_fields=['trial_emails_sent'])
        except Exception:
            logger.exception(
                'process_trial_statuses failed for tenant %s', tenant.schema_name
            )
```

- [ ] **Step 4: Run all members tests — expect 21 green**

```bash
python -m pytest apps/members/tests.py -v
```

Expected: 21 tests PASSED across all 4 test classes.

- [ ] **Step 5: Commit**

```bash
git add apps/members/tasks.py apps/members/tests.py
git commit -m "feat: add process_trial_statuses and _send_trial_email with tests"
```

---

## Task 7: Celery Beat Schedule

**Files:**
- Modify: `config/settings/base.py`

- [ ] **Step 1: Add 3 entries to CELERY_BEAT_SCHEDULE**

In `config/settings/base.py`, find the existing `CELERY_BEAT_SCHEDULE` (lines 194–199):

```python
CELERY_BEAT_SCHEDULE = {
    'process-no-shows-every-15-min': {
        'task': 'apps.billing.tasks.process_no_shows',
        'schedule': crontab(minute='*/15'),
    },
}
```

Replace with:

```python
CELERY_BEAT_SCHEDULE = {
    'process-no-shows-every-15-min': {
        'task': 'apps.billing.tasks.process_no_shows',
        'schedule': crontab(minute='*/15'),
    },
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
}
```

- [ ] **Step 2: Run full test suite**

```bash
python -m pytest apps/members/tests.py apps/billing/tests.py apps/scheduling/tests.py -v
```

Expected: All tests PASSED (21 + 10 + 3 = 34 tests).

- [ ] **Step 3: Commit**

```bash
git add config/settings/base.py
git commit -m "feat: register retention Celery beat tasks — check_member_retention, send_birthday_messages, process_trial_statuses"
```

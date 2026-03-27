"""
Unit tests for apps/members/tasks.py.

All model access is mocked — these tests run without a tenant DB context.
Uses SimpleTestCase so Django doesn't set up a database at all.
"""
import datetime
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone

import apps.members.tasks  # noqa: F401 — ensure module is in sys.modules so patch() can resolve it


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
        kwargs = MockFCM.return_value.notify_single_device.call_args.kwargs
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
        kwargs = mock_mail.call_args.kwargs
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
        kwargs = MockFCM.return_value.notify_single_device.call_args.kwargs
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
        assert 'Test Gym' in mock_mail.call_args.kwargs['subject']
        assert '100' in mock_mail.call_args.kwargs['message']

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

    def test_continues_to_next_tenant_on_exception(self):
        """Per-tenant exception is caught; other tenants are still processed."""
        tenant1 = _make_tenant()
        tenant2 = _make_tenant()
        member = _make_member()
        call_count = {'n': 0}

        def fake_schema_ctx(schema_name):
            call_count['n'] += 1
            if call_count['n'] == 1:
                raise Exception('schema error')
            return MagicMock()

        with patch('apps.members.tasks.GymTenant') as MockTenant, \
             patch('apps.members.tasks.schema_context', side_effect=fake_schema_ctx), \
             patch('apps.members.tasks.MemberProfile') as MockMember, \
             patch('apps.members.tasks.award_loyalty_points', return_value=50) as mock_award, \
             patch('apps.members.tasks.FCMNotification'), \
             patch('apps.members.tasks.send_mail'):
            MockTenant.objects.filter.return_value = [tenant1, tenant2]
            (MockMember.objects.filter.return_value
             .select_related.return_value) = [member]
            from apps.members.tasks import send_birthday_messages
            send_birthday_messages()  # must not raise

        mock_award.assert_called_once_with(member, 'birthday', description='Happy Birthday!')

    def test_push_exception_does_not_prevent_email(self):
        """If FCM push raises, email is still sent for that member."""
        member = _make_member(fcm_token='tok')
        with patch('apps.members.tasks.GymTenant') as MockTenant, \
             patch('apps.members.tasks.schema_context'), \
             patch('apps.members.tasks.MemberProfile') as MockMember, \
             patch('apps.members.tasks.award_loyalty_points', return_value=50), \
             patch('apps.members.tasks.FCMNotification') as MockFCM, \
             patch('apps.members.tasks.send_mail') as mock_mail:
            MockTenant.objects.filter.return_value = [_make_tenant()]
            (MockMember.objects.filter.return_value
             .select_related.return_value) = [member]
            MockFCM.return_value.notify_single_device.side_effect = Exception('FCM down')
            from apps.members.tasks import send_birthday_messages
            send_birthday_messages()  # must not raise
        mock_mail.assert_called_once()


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
        update_fields = tenant.save.call_args.kwargs['update_fields']
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

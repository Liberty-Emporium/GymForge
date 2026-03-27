"""
Unit tests for apps/billing/tasks.py.

All model access is mocked — these tests run without a tenant DB context.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


def _make_booking(stripe_customer_id='cus_abc123'):
    """Return (booking, member, membership) MagicMocks wired together."""
    membership = MagicMock()
    membership.stripe_customer_id = stripe_customer_id

    member = MagicMock()
    member.active_membership = membership
    member.user.email = 'member@example.com'

    booking = MagicMock()
    booking.pk = 42
    booking.member = member
    booking.no_show_fee_charged = False
    return booking, member, membership


class ChargeNoShowFeeTest(SimpleTestCase):
    """Tests for charge_no_show_fee(booking, fee_amount, charge_type)."""

    def test_missing_stripe_customer_id_creates_failed_charge_and_returns(self):
        """If stripe_customer_id is blank, record failed charge and stop — no Stripe call."""
        booking, member, membership = _make_booking(stripe_customer_id='')

        with patch('apps.billing.tasks.NoShowCharge') as MockCharge, \
             patch('apps.billing.tasks.stripe') as mock_stripe:
            from apps.billing.tasks import charge_no_show_fee
            charge_no_show_fee(booking, Decimal('10.00'), 'no_show')

        MockCharge.objects.create.assert_called_once_with(
            member=member,
            booking=booking,
            amount=Decimal('10.00'),
            charge_type='no_show',
            status='failed',
        )
        mock_stripe.PaymentIntent.create.assert_not_called()
        booking.save.assert_not_called()

    def test_missing_active_membership_creates_failed_charge(self):
        """If member has no active membership, record failed charge and stop."""
        booking, member, _ = _make_booking()
        member.active_membership = None

        with patch('apps.billing.tasks.NoShowCharge') as MockCharge, \
             patch('apps.billing.tasks.stripe') as mock_stripe:
            from apps.billing.tasks import charge_no_show_fee
            charge_no_show_fee(booking, Decimal('10.00'), 'no_show')

        MockCharge.objects.create.assert_called_once_with(
            member=member,
            booking=booking,
            amount=Decimal('10.00'),
            charge_type='no_show',
            status='failed',
        )
        mock_stripe.PaymentIntent.create.assert_not_called()

    def test_stripe_success_creates_completed_charge_and_marks_booking(self):
        """Successful Stripe charge: create completed NoShowCharge and set no_show_fee_charged=True."""
        booking, member, membership = _make_booking(stripe_customer_id='cus_abc123')
        mock_intent = MagicMock()
        mock_intent.id = 'pi_test_123'

        with patch('apps.billing.tasks.stripe') as mock_stripe, \
             patch('apps.billing.tasks.NoShowCharge') as MockCharge, \
             patch('apps.billing.tasks.send_mail') as mock_mail:
            mock_stripe.PaymentIntent.create.return_value = mock_intent
            from apps.billing.tasks import charge_no_show_fee
            charge_no_show_fee(booking, Decimal('10.00'), 'no_show')

        mock_stripe.PaymentIntent.create.assert_called_once_with(
            amount=1000,  # $10.00 in cents
            currency='usd',
            customer='cus_abc123',
            confirm=True,
            off_session=True,
        )
        MockCharge.objects.create.assert_called_once_with(
            member=member,
            booking=booking,
            amount=Decimal('10.00'),
            charge_type='no_show',
            stripe_payment_intent='pi_test_123',
            status='completed',
        )
        assert booking.no_show_fee_charged is True
        booking.save.assert_called_once_with(update_fields=['no_show_fee_charged'])
        mock_mail.assert_called_once()  # notification sent

    def test_stripe_success_sends_correct_email_subject_for_no_show(self):
        """Email subject should mention no-show."""
        booking, member, membership = _make_booking(stripe_customer_id='cus_abc123')
        mock_intent = MagicMock()
        mock_intent.id = 'pi_test_456'

        with patch('apps.billing.tasks.stripe') as mock_stripe, \
             patch('apps.billing.tasks.NoShowCharge'), \
             patch('apps.billing.tasks.send_mail') as mock_mail:
            mock_stripe.PaymentIntent.create.return_value = mock_intent
            from apps.billing.tasks import charge_no_show_fee
            charge_no_show_fee(booking, Decimal('5.00'), 'no_show')

        call_kwargs = mock_mail.call_args
        subject = call_kwargs[1].get('subject') or call_kwargs[0][0]
        assert 'no-show' in subject.lower() or 'no show' in subject.lower()

    def test_stripe_success_sends_correct_email_subject_for_late_cancel(self):
        """Email subject should mention late cancellation."""
        booking, member, membership = _make_booking(stripe_customer_id='cus_abc123')
        mock_intent = MagicMock()
        mock_intent.id = 'pi_test_789'

        with patch('apps.billing.tasks.stripe') as mock_stripe, \
             patch('apps.billing.tasks.NoShowCharge'), \
             patch('apps.billing.tasks.send_mail') as mock_mail:
            mock_stripe.PaymentIntent.create.return_value = mock_intent
            from apps.billing.tasks import charge_no_show_fee
            charge_no_show_fee(booking, Decimal('5.00'), 'late_cancel')

        call_kwargs = mock_mail.call_args
        subject = call_kwargs[1].get('subject') or call_kwargs[0][0]
        assert 'cancel' in subject.lower()

    def test_stripe_error_creates_failed_charge_and_does_not_raise(self):
        """StripeError must be caught: create failed NoShowCharge, never raise."""
        booking, member, membership = _make_booking(stripe_customer_id='cus_abc123')

        with patch('apps.billing.tasks.stripe') as mock_stripe, \
             patch('apps.billing.tasks.NoShowCharge') as MockCharge:
            mock_stripe.error.StripeError = Exception
            mock_stripe.PaymentIntent.create.side_effect = Exception('card_declined')
            from apps.billing.tasks import charge_no_show_fee
            # Must not raise
            charge_no_show_fee(booking, Decimal('10.00'), 'no_show')

        MockCharge.objects.create.assert_called_once_with(
            member=member,
            booking=booking,
            amount=Decimal('10.00'),
            charge_type='no_show',
            status='failed',
        )
        booking.save.assert_not_called()


class ProcessNoShowsTest(SimpleTestCase):
    """Tests for process_no_shows Celery task."""

    def _make_tenant(self, schema_name='testgym'):
        tenant = MagicMock()
        tenant.schema_name = schema_name
        return tenant

    def _make_booking_for_task(self, no_show_fee=Decimal('10.00'), stripe_customer_id='cus_abc'):
        tier = MagicMock()
        tier.no_show_fee = no_show_fee

        membership = MagicMock()
        membership.stripe_customer_id = stripe_customer_id
        membership.tier = tier

        member = MagicMock()
        member.active_membership = membership

        booking = MagicMock()
        booking.pk = 99
        booking.member = member
        booking.no_show_fee_charged = False
        booking.status = 'confirmed'
        return booking

    def test_marks_booking_as_no_show_and_charges_fee(self):
        """process_no_shows marks confirmed bookings no_show and calls charge_no_show_fee."""
        tenant = self._make_tenant()
        booking = self._make_booking_for_task(no_show_fee=Decimal('15.00'))

        with patch('apps.billing.tasks.GymTenant') as MockTenant, \
             patch('apps.billing.tasks.schema_context') as mock_ctx, \
             patch('apps.billing.tasks.Booking') as MockBooking, \
             patch('apps.billing.tasks.charge_no_show_fee') as mock_charge, \
             patch('apps.billing.tasks.timezone') as mock_tz:
            MockTenant.objects.filter.return_value = [tenant]
            mock_ctx.return_value.__enter__ = lambda s: s
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            MockBooking.objects.filter.return_value.select_related.return_value \
                .prefetch_related.return_value = [booking]

            from apps.billing.tasks import process_no_shows
            process_no_shows()

        assert booking.status == 'no_show'
        booking.save.assert_any_call(update_fields=['status'])
        mock_charge.assert_called_once_with(booking, Decimal('15.00'), 'no_show')

    def test_marks_fee_charged_when_tier_fee_is_zero_no_stripe_call(self):
        """When no_show_fee == 0, mark no_show_fee_charged=True but skip Stripe."""
        tenant = self._make_tenant()
        booking = self._make_booking_for_task(no_show_fee=Decimal('0.00'))

        with patch('apps.billing.tasks.GymTenant') as MockTenant, \
             patch('apps.billing.tasks.schema_context') as mock_ctx, \
             patch('apps.billing.tasks.Booking') as MockBooking, \
             patch('apps.billing.tasks.charge_no_show_fee') as mock_charge, \
             patch('apps.billing.tasks.timezone'):
            MockTenant.objects.filter.return_value = [tenant]
            mock_ctx.return_value.__enter__ = lambda s: s
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            MockBooking.objects.filter.return_value.select_related.return_value \
                .prefetch_related.return_value = [booking]

            from apps.billing.tasks import process_no_shows
            process_no_shows()

        mock_charge.assert_not_called()
        assert booking.no_show_fee_charged is True
        booking.save.assert_any_call(update_fields=['status'])

    def test_marks_fee_charged_when_member_has_no_active_membership(self):
        """No active membership: mark no_show_fee_charged=True, skip charge."""
        tenant = self._make_tenant()
        booking = self._make_booking_for_task()
        booking.member.active_membership = None

        with patch('apps.billing.tasks.GymTenant') as MockTenant, \
             patch('apps.billing.tasks.schema_context') as mock_ctx, \
             patch('apps.billing.tasks.Booking') as MockBooking, \
             patch('apps.billing.tasks.charge_no_show_fee') as mock_charge, \
             patch('apps.billing.tasks.timezone'):
            MockTenant.objects.filter.return_value = [tenant]
            mock_ctx.return_value.__enter__ = lambda s: s
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            MockBooking.objects.filter.return_value.select_related.return_value \
                .prefetch_related.return_value = [booking]

            from apps.billing.tasks import process_no_shows
            process_no_shows()

        mock_charge.assert_not_called()
        assert booking.no_show_fee_charged is True
        booking.save.assert_any_call(update_fields=['no_show_fee_charged'])

    def test_continues_to_next_tenant_on_exception(self):
        """An exception in one tenant must not abort processing of subsequent tenants."""
        tenant1 = self._make_tenant('gym1')
        tenant2 = self._make_tenant('gym2')
        booking2 = self._make_booking_for_task(no_show_fee=Decimal('5.00'))

        call_count = 0

        def fake_context(schema_name):
            nonlocal call_count
            call_count += 1
            ctx = MagicMock()
            if schema_name == 'gym1':
                ctx.__enter__ = MagicMock(side_effect=Exception('DB error'))
            else:
                ctx.__enter__ = lambda s: s
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        with patch('apps.billing.tasks.GymTenant') as MockTenant, \
             patch('apps.billing.tasks.schema_context', side_effect=fake_context), \
             patch('apps.billing.tasks.Booking') as MockBooking, \
             patch('apps.billing.tasks.charge_no_show_fee') as mock_charge, \
             patch('apps.billing.tasks.timezone'):
            MockTenant.objects.filter.return_value = [tenant1, tenant2]
            MockBooking.objects.filter.return_value.select_related.return_value \
                .prefetch_related.return_value = [booking2]

            from apps.billing.tasks import process_no_shows
            process_no_shows()  # must not raise

        # Both tenants were attempted
        assert call_count == 2
        # gym2 was still processed
        mock_charge.assert_called_once()

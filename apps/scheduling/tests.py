"""
Unit tests for apps/scheduling/views.py — cancel_booking late-cancel path.

Mocks the model layer so no tenant DB context is required.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


class CancelBookingLateCancelTest(SimpleTestCase):
    """Test that cancel_booking calls charge_no_show_fee for inside-window cancels."""

    def _make_request_and_booking(self, late_cancel_fee=Decimal('8.00'), inside_window=True):
        """Return (request, booking, member) with all collaborators mocked."""
        tier = MagicMock()
        tier.cancellation_window_hours = 2
        tier.late_cancel_fee = late_cancel_fee

        membership = MagicMock()
        membership.tier = tier

        member = MagicMock()
        member.active_membership = membership

        import datetime
        from django.utils import timezone as tz
        now = tz.now()
        if inside_window:
            # class starts in 1 hour — inside the 2h window
            session_start = now + datetime.timedelta(hours=1)
        else:
            # class starts in 3 hours — outside the 2h window
            session_start = now + datetime.timedelta(hours=3)

        session = MagicMock()
        session.start_datetime = session_start

        booking = MagicMock()
        booking.pk = 7
        booking.status = 'confirmed'
        booking.class_session = session
        booking.member = member

        user = MagicMock()
        user.is_authenticated = True
        user.role = 'member'
        user.member_profile = member

        request = MagicMock()
        request.user = user
        request.method = 'POST'

        return request, booking, member

    def test_inside_window_with_fee_calls_charge_no_show_fee(self):
        """Late cancel inside window with fee > 0 must call charge_no_show_fee."""
        request, booking, member = self._make_request_and_booking(
            late_cancel_fee=Decimal('8.00'), inside_window=True
        )

        with patch('apps.scheduling.views._get_member', return_value=member), \
             patch('apps.scheduling.views.get_object_or_404', return_value=booking), \
             patch('apps.scheduling.views.charge_no_show_fee') as mock_charge, \
             patch('apps.scheduling.views._promote_waitlist'), \
             patch('apps.scheduling.views._booking_button_partial', return_value=MagicMock()):
            from apps.scheduling.views import cancel_booking
            cancel_booking(request, booking_id=7)

        mock_charge.assert_called_once_with(booking, Decimal('8.00'), 'late_cancel')

    def test_inside_window_zero_fee_does_not_call_charge_no_show_fee(self):
        """Late cancel inside window but fee == 0 must NOT call charge_no_show_fee."""
        request, booking, member = self._make_request_and_booking(
            late_cancel_fee=Decimal('0.00'), inside_window=True
        )

        with patch('apps.scheduling.views._get_member', return_value=member), \
             patch('apps.scheduling.views.get_object_or_404', return_value=booking), \
             patch('apps.scheduling.views.charge_no_show_fee') as mock_charge, \
             patch('apps.scheduling.views._promote_waitlist'), \
             patch('apps.scheduling.views._booking_button_partial', return_value=MagicMock()):
            from apps.scheduling.views import cancel_booking
            cancel_booking(request, booking_id=7)

        mock_charge.assert_not_called()

    def test_outside_window_does_not_call_charge_no_show_fee(self):
        """Cancel outside the window sets status='cancelled' without any fee."""
        request, booking, member = self._make_request_and_booking(
            late_cancel_fee=Decimal('8.00'), inside_window=False
        )

        with patch('apps.scheduling.views._get_member', return_value=member), \
             patch('apps.scheduling.views.get_object_or_404', return_value=booking), \
             patch('apps.scheduling.views.charge_no_show_fee') as mock_charge, \
             patch('apps.scheduling.views._promote_waitlist'), \
             patch('apps.scheduling.views._booking_button_partial', return_value=MagicMock()):
            from apps.scheduling.views import cancel_booking
            cancel_booking(request, booking_id=7)

        mock_charge.assert_not_called()
        assert booking.status == 'cancelled'

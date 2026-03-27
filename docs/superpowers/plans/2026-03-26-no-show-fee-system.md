# No-Show Fee System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate Stripe charges for member no-shows and late cancellations, with failed charges flagged for manual review.

**Architecture:** A shared `charge_no_show_fee()` helper in `apps/billing/tasks.py` handles the Stripe call, NoShowCharge creation, and email notification. It is called from two entry points: the `process_no_shows` Celery beat task (no-shows, every 15 min) and the existing `cancel_booking` view (late cancels). `MemberMembership` gets a `stripe_customer_id` field to support per-member charges.

**Tech Stack:** Django 5, Celery + django-celery-beat, Stripe Python SDK, Django send_mail (SendGrid via django-anymail), unittest.mock for tests.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `apps/billing/models.py` | Modify | Add `stripe_customer_id` to `MemberMembership` |
| `apps/billing/migrations/0003_membermembership_stripe_customer_id.py` | Create (makemigrations) | Schema migration |
| `apps/billing/tasks.py` | Create | `charge_no_show_fee()` helper + `process_no_shows` task |
| `apps/billing/tests.py` | Create | Unit tests for tasks |
| `apps/scheduling/views.py` | Modify | Replace placeholder NoShowCharge.create with `charge_no_show_fee()` call |
| `apps/scheduling/tests.py` | Create | Test cancel_booking late-cancel path calls charge_no_show_fee |
| `config/settings/base.py` | Modify | Add `CELERY_BEAT_SCHEDULE` |

---

## Task 1: Add `stripe_customer_id` to `MemberMembership`

**Files:**
- Modify: `apps/billing/models.py`
- Create: `apps/billing/migrations/0003_membermembership_stripe_customer_id.py` (via makemigrations)

- [ ] **Step 1: Add the field to MemberMembership**

In `apps/billing/models.py`, find the `MemberMembership` class. Add `stripe_customer_id` directly after `stripe_subscription_id` (line ~114):

```python
    stripe_subscription_id = models.CharField(max_length=100, blank=True)
    stripe_customer_id = models.CharField(max_length=100, blank=True)
```

- [ ] **Step 2: Generate the migration**

```bash
cd "/home/mingo/Documents/Finished APPs for Demos/GymForge"
python manage.py makemigrations billing --name membermembership_stripe_customer_id
```

Expected output:
```
Migrations for 'billing':
  apps/billing/migrations/0003_membermembership_stripe_customer_id.py
    - Add field stripe_customer_id to membermembership
```

- [ ] **Step 3: Apply the migration**

```bash
python manage.py migrate billing
```

Expected output ends with:
```
  Applying billing.0003_membermembership_stripe_customer_id... OK
```

- [ ] **Step 4: Verify Django system check passes**

```bash
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Commit**

```bash
git add apps/billing/models.py apps/billing/migrations/0003_membermembership_stripe_customer_id.py
git commit -m "feat(billing): add stripe_customer_id to MemberMembership"
```

---

## Task 2: `charge_no_show_fee()` helper with tests

**Files:**
- Create: `apps/billing/tasks.py`
- Create: `apps/billing/tests.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/billing/tests.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail (tasks.py doesn't exist yet)**

```bash
cd "/home/mingo/Documents/Finished APPs for Demos/GymForge"
python manage.py test apps.billing.tests.ChargeNoShowFeeTest --verbosity=2 2>&1 | head -30
```

Expected: errors like `ModuleNotFoundError: No module named 'apps.billing.tasks'` or `ImportError`.

- [ ] **Step 3: Create `apps/billing/tasks.py` with `charge_no_show_fee()`**

Create `apps/billing/tasks.py`:

```python
"""
Billing Celery tasks.

charge_no_show_fee — shared helper for no-show and late-cancel Stripe charges.
    Called by: process_no_shows task (no-shows) and cancel_booking view (late cancels).

process_no_shows — periodic task (every 15 min via Celery beat).
    Scans all tenant schemas for confirmed bookings where the class ended
    more than 30 minutes ago and charges have not yet been processed.
"""
import logging
from decimal import Decimal

import stripe
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from apps.billing.models import NoShowCharge

logger = logging.getLogger(__name__)


def charge_no_show_fee(booking, fee_amount, charge_type):
    """
    Charge a no-show or late-cancel fee to the member's saved Stripe customer.

    Args:
        booking    : Booking instance (status already set by caller)
        fee_amount : Decimal — from MembershipTier.no_show_fee or .late_cancel_fee
        charge_type: 'no_show' or 'late_cancel'

    Side effects:
        - Creates a NoShowCharge record (status='completed' or 'failed')
        - Sets booking.no_show_fee_charged=True on success
        - Sends notification email to member on success
        - Never raises — all Stripe errors are caught and logged
    """
    member = booking.member
    membership = member.active_membership

    if not membership or not membership.stripe_customer_id:
        logger.warning(
            'No stripe_customer_id for member %s (booking %s) — skipping charge',
            member,
            booking.pk,
        )
        NoShowCharge.objects.create(
            member=member,
            booking=booking,
            amount=fee_amount,
            charge_type=charge_type,
            status='failed',
        )
        return

    stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', '')
    amount_cents = int(fee_amount * 100)

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='usd',
            customer=membership.stripe_customer_id,
            confirm=True,
            off_session=True,
        )
        NoShowCharge.objects.create(
            member=member,
            booking=booking,
            amount=fee_amount,
            charge_type=charge_type,
            stripe_payment_intent=intent.id,
            status='completed',
        )
        booking.no_show_fee_charged = True
        booking.save(update_fields=['no_show_fee_charged'])

        subject = (
            'No-show fee charged'
            if charge_type == 'no_show'
            else 'Late cancellation fee charged'
        )
        send_mail(
            subject=subject,
            message=(
                f'Hi {member.user.get_full_name() or member.user.username},\n\n'
                f'A ${fee_amount:.2f} {subject.lower()} has been applied to your account.\n\n'
                f'If you have any questions, please contact the gym.\n'
            ),
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@gymforge.com'),
            recipient_list=[member.user.email],
            fail_silently=True,
        )

    except stripe.error.StripeError as e:
        logger.error('Stripe charge failed for booking %s: %s', booking.pk, e)
        NoShowCharge.objects.create(
            member=member,
            booking=booking,
            amount=fee_amount,
            charge_type=charge_type,
            status='failed',
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python manage.py test apps.billing.tests.ChargeNoShowFeeTest --verbosity=2
```

Expected: `OK` with 6 tests passing.

- [ ] **Step 5: Commit**

```bash
git add apps/billing/tasks.py apps/billing/tests.py
git commit -m "feat(billing): add charge_no_show_fee helper with tests"
```

---

## Task 3: `process_no_shows` Celery task with tests

**Files:**
- Modify: `apps/billing/tasks.py` (add `process_no_shows`)
- Modify: `apps/billing/tests.py` (add `ProcessNoShowsTest`)

- [ ] **Step 1: Write the failing tests**

Append to `apps/billing/tests.py`:

```python


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

        # gym2 was still processed
        mock_charge.assert_called_once()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python manage.py test apps.billing.tests.ProcessNoShowsTest --verbosity=2 2>&1 | head -20
```

Expected: `AttributeError` or `ImportError` — `process_no_shows` not defined yet.

- [ ] **Step 3: Add `process_no_shows` to `apps/billing/tasks.py`**

Add these imports at the top of `apps/billing/tasks.py` (after the existing imports):

```python
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
```

Then append the task at the bottom of `apps/billing/tasks.py`:

```python


@shared_task
def process_no_shows():
    """
    Scan all active tenant schemas for no-shows and charge fees.

    Runs every 15 minutes via Celery beat. A no-show is a Booking with:
      - status='confirmed'
      - no_show_fee_charged=False
      - class_session.end_datetime < now - 30 minutes
    """
    from django_tenants.utils import schema_context
    from apps.tenants.models import GymTenant
    from apps.scheduling.models import Booking

    cutoff = timezone.now() - timedelta(minutes=30)
    tenants = GymTenant.objects.filter(subscription_status__in=['trial', 'active'])

    for tenant in tenants:
        try:
            with schema_context(tenant.schema_name):
                bookings = (
                    Booking.objects
                    .filter(
                        status='confirmed',
                        no_show_fee_charged=False,
                        class_session__end_datetime__lt=cutoff,
                    )
                    .select_related('member__user', 'class_session')
                    .prefetch_related('member__memberships__tier')
                )
                for booking in bookings:
                    booking.status = 'no_show'
                    booking.save(update_fields=['status'])

                    membership = booking.member.active_membership
                    if membership and membership.tier.no_show_fee > 0:
                        charge_no_show_fee(
                            booking,
                            membership.tier.no_show_fee,
                            'no_show',
                        )
                    else:
                        booking.no_show_fee_charged = True
                        booking.save(update_fields=['no_show_fee_charged'])

        except Exception:
            logger.exception(
                'process_no_shows failed for tenant %s', tenant.schema_name
            )
```

- [ ] **Step 4: Run all billing tests to verify they pass**

```bash
python manage.py test apps.billing.tests --verbosity=2
```

Expected: `OK` with all 10 tests passing.

- [ ] **Step 5: Commit**

```bash
git add apps/billing/tasks.py apps/billing/tests.py
git commit -m "feat(billing): add process_no_shows Celery task with tests"
```

---

## Task 4: Update `cancel_booking` to call `charge_no_show_fee`

**Files:**
- Modify: `apps/scheduling/views.py`
- Create: `apps/scheduling/tests.py`

- [ ] **Step 1: Write the failing test**

Create `apps/scheduling/tests.py`:

```python
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
        """Return (request, booking_id) with all collaborators mocked."""
        tier = MagicMock()
        tier.cancellation_window_hours = 2
        tier.late_cancel_fee = late_cancel_fee

        membership = MagicMock()
        membership.tier = tier

        member = MagicMock()
        member.active_membership = membership

        session = MagicMock()
        # start_datetime - 2h = cutoff; if inside_window, now() > cutoff
        import datetime
        from django.utils import timezone as tz
        now = tz.now()
        if inside_window:
            # class starts in 1 hour — inside the 2h window
            session.start_datetime = now + datetime.timedelta(hours=1)
        else:
            # class starts in 3 hours — outside the 2h window
            session.start_datetime = now + datetime.timedelta(hours=3)

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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python manage.py test apps.scheduling.tests.CancelBookingLateCancelTest --verbosity=2 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'charge_no_show_fee' from 'apps.scheduling.views'`

- [ ] **Step 3: Update `apps/scheduling/views.py`**

**3a.** In the imports at the top of `apps/scheduling/views.py`, add the `charge_no_show_fee` import and remove `NoShowCharge` (it's no longer used directly):

```python
# Replace line 16:
from apps.billing.models import MemberMembership, NoShowCharge

# With:
from apps.billing.models import MemberMembership
from apps.billing.tasks import charge_no_show_fee
```

**3b.** In the `cancel_booking` view, replace the `NoShowCharge.objects.create(...)` block (~lines 194–201):

```python
# Remove this entire block:
            if fee and fee > 0:
                NoShowCharge.objects.create(
                    member=member,
                    booking=booking,
                    amount=fee,
                    charge_type='late_cancel',
                    status='pending',
                )

# Replace with:
            if fee and fee > 0:
                charge_no_show_fee(booking, fee, 'late_cancel')
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python manage.py test apps.scheduling.tests.CancelBookingLateCancelTest --verbosity=2
```

Expected: `OK` with 3 tests passing.

- [ ] **Step 5: Run system check to confirm no import errors**

```bash
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 6: Commit**

```bash
git add apps/scheduling/views.py apps/scheduling/tests.py
git commit -m "feat(scheduling): wire cancel_booking to charge_no_show_fee"
```

---

## Task 5: Register Celery beat schedule

**Files:**
- Modify: `config/settings/base.py`

- [ ] **Step 1: Add `CELERY_BEAT_SCHEDULE` to settings**

In `config/settings/base.py`, find the Celery section (around line 188 where `CELERY_TASK_SERIALIZER` is defined). Add the beat schedule immediately after `CELERY_BEAT_SCHEDULER`:

```python
# Find this line (around line 191):
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Add directly after it:
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'process-no-shows-every-15-min': {
        'task': 'apps.billing.tasks.process_no_shows',
        'schedule': crontab(minute='*/15'),
    },
}
```

- [ ] **Step 2: Verify Django system check passes**

```bash
cd "/home/mingo/Documents/Finished APPs for Demos/GymForge"
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 3: Verify task is importable by Celery**

```bash
python -c "from apps.billing.tasks import process_no_shows; print('OK:', process_no_shows.name if hasattr(process_no_shows, 'name') else process_no_shows)"
```

Expected: `OK: apps.billing.tasks.process_no_shows`

- [ ] **Step 4: Run the full test suite to confirm nothing broken**

```bash
python manage.py test apps.billing.tests apps.scheduling.tests --verbosity=2
```

Expected: `OK` with all 13 tests passing.

- [ ] **Step 5: Commit**

```bash
git add config/settings/base.py
git commit -m "feat(billing): register process_no_shows in Celery beat schedule"
```

---

## Summary

After all 5 tasks:

| Capability | Entry point |
|---|---|
| No-show detected | `process_no_shows` runs every 15 min, marks `status='no_show'`, charges via Stripe |
| Late cancel charged | `cancel_booking` view calls `charge_no_show_fee()` inline when inside window |
| Stripe failure handled | `NoShowCharge(status='failed')` created, viewable in Django admin |
| Zero-fee tiers | `no_show_fee_charged=True` set without Stripe call, prevents re-processing |
| Member notified | `send_mail` on successful charge (fail_silently=True) |

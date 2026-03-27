# No-Show Fee System — Design Spec
**Step 43 · GymForge v2**
Date: 2026-03-26

---

## Overview

Automates charging members for no-shows and late cancellations via Stripe PaymentIntent.
Two entry points: a Celery beat task for no-shows (every 15 min) and an inline call from
the existing `cancel_booking` view for late cancels. Failed charges are flagged for manual
review via `NoShowCharge(status='failed')`.

---

## 1. Schema Change — `MemberMembership.stripe_customer_id`

**File:** `apps/billing/models.py`
**Migration:** `apps/billing/migrations/0003_membermembership_stripe_customer_id.py`

Add one field to `MemberMembership`:

```python
stripe_customer_id = models.CharField(max_length=100, blank=True)
```

Sits alongside the existing `stripe_subscription_id`. Populated when a member subscribes
(outside the scope of this step — seeded as blank, charge skips gracefully if absent).

---

## 2. `apps/billing/tasks.py` — New File

### `charge_no_show_fee(booking, fee_amount, charge_type)`

Shared helper called by both the Celery task and the cancel view.

**Inputs:**
- `booking` — `Booking` instance (already has `status` set by caller)
- `fee_amount` — `Decimal` from `MembershipTier.no_show_fee` or `late_cancel_fee`
- `charge_type` — `'no_show'` or `'late_cancel'`

**Flow:**
1. Get `member = booking.member` (MemberProfile)
2. Get `membership = member.active_membership`
3. If no membership or `membership.stripe_customer_id` is blank:
   - Log warning: `f"No stripe_customer_id for {member} — skipping charge"`
   - Create `NoShowCharge(member=member, booking=booking, amount=fee_amount, charge_type=charge_type, status='failed')`
   - Return
4. Convert `fee_amount` to integer cents: `int(fee_amount * 100)`
5. Call `stripe.PaymentIntent.create(amount=cents, currency='usd', customer=membership.stripe_customer_id, confirm=True, off_session=True)`
6. On success:
   - `NoShowCharge.objects.create(member=member, booking=booking, amount=fee_amount, charge_type=charge_type, stripe_payment_intent=pi.id, status='completed')`
   - `booking.no_show_fee_charged = True; booking.save(update_fields=['no_show_fee_charged'])`
   - Send email: `send_mail(...)` to `member.user.email`, subject `"No-show fee charged"` or `"Late cancellation fee charged"`, `fail_silently=True`
7. On `stripe.error.StripeError`:
   - `logger.error(f"Stripe charge failed for booking {booking.pk}: {e}")`
   - `NoShowCharge.objects.create(..., status='failed')`
   - Do NOT re-raise — never crash the task

### `process_no_shows` Celery Task

```python
@shared_task
def process_no_shows():
```

**Schedule:** Every 15 minutes via `CELERY_BEAT_SCHEDULE`.

**Flow:**
1. Import `GymTenant` from `apps.tenants.models`
2. Get all active tenants: `GymTenant.objects.filter(subscription_status__in=['trial', 'active'])`
3. For each tenant, run inside `schema_context(tenant.schema_name)`:
   a. Compute cutoff: `now - timedelta(minutes=30)`
   b. Query: `Booking.objects.filter(status='confirmed', no_show_fee_charged=False, class_session__end_datetime__lt=cutoff).select_related('member__user', 'class_session').prefetch_related('member__memberships__tier')`
   c. For each booking:
      - `booking.status = 'no_show'`
      - `booking.save(update_fields=['status'])`
      - `membership = booking.member.active_membership`
      - If membership and `membership.tier.no_show_fee > 0`:
        - Call `charge_no_show_fee(booking, membership.tier.no_show_fee, 'no_show')`
      - Else: just set `booking.no_show_fee_charged = True` and save (mark as processed, no charge)
4. Outer try/except: log any unhandled exceptions per tenant, continue to next tenant

**Important:** `process_no_shows` sets `booking.no_show_fee_charged=True` even when no fee applies
(tier fee is $0.00) to prevent re-processing on subsequent runs.

---

## 3. `apps/scheduling/views.py` — Update `cancel_booking`

**Replace** the existing `NoShowCharge.objects.create(status='pending')` block with a call to
`charge_no_show_fee()`:

```python
# Before (placeholder):
NoShowCharge.objects.create(
    member=member,
    booking=booking,
    amount=fee,
    charge_type='late_cancel',
    status='pending',
)

# After:
from apps.billing.tasks import charge_no_show_fee
charge_no_show_fee(booking, fee, 'late_cancel')
```

The `charge_no_show_fee` function handles `NoShowCharge` creation and error handling internally.
Move the import to the top of `views.py` (not inline).

---

## 4. `config/settings/base.py` — Celery Beat Schedule

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'process-no-shows-every-15-min': {
        'task': 'apps.billing.tasks.process_no_shows',
        'schedule': crontab(minute='*/15'),
    },
}
```

The `DatabaseScheduler` is already configured (`CELERY_BEAT_SCHEDULER`). Adding
`CELERY_BEAT_SCHEDULE` to settings seeds the initial schedule; the DB scheduler manages
runtime overrides.

---

## 5. Files Changed / Created

| File | Action |
|------|--------|
| `apps/billing/tasks.py` | Create |
| `apps/billing/models.py` | Add `stripe_customer_id` to `MemberMembership` |
| `apps/billing/migrations/0003_membermembership_stripe_customer_id.py` | Create (via makemigrations) |
| `apps/scheduling/views.py` | Update `cancel_booking` to call `charge_no_show_fee` |
| `config/settings/base.py` | Add `CELERY_BEAT_SCHEDULE` |

---

## 6. Error Handling & Manual Review

- `NoShowCharge(status='failed')` is created on any Stripe failure or missing customer ID
- Owner can query these in Django admin (already registered)
- Logging uses the standard Python `logging` module: `logger = logging.getLogger(__name__)`
- Task failures per-tenant are caught and logged; the task continues to the next tenant

---

## 7. Out of Scope

- Owner-facing UI to list/retry failed charges (future step)
- Populating `stripe_customer_id` on existing memberships (Step 47 / Stripe webhook)
- Refund flow for disputed no-show charges

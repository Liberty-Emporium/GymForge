# GymForge Step 42 — Payroll Tracking Design

**Date:** 2026-03-25
**Status:** Approved

---

## Overview

Build the complete `/owner/payroll/` section for gym owner payroll management. Covers pay rate CRUD, payroll period generation, period detail with CSV export, and pay rate history per staff member. All views are restricted to `gym_owner` role.

---

## Existing Models (no migrations needed)

Both models are fully defined and migrated in `apps/payroll/models.py`.

### StaffPayRate

| Field | Type | Notes |
|---|---|---|
| `staff` | FK → User | The staff member |
| `pay_type` | CharField | `hourly`, `salary`, `per_class`, `commission` |
| `rate` | DecimalField | Hourly rate, monthly salary amount, or per-class fee |
| `location` | FK → Location (nullable) | Blank = all locations |
| `effective_from` | DateField | When this rate takes effect |
| `effective_to` | DateField (nullable) | Null = currently active |
| `notes` | TextField | Optional |

**Spec term mapping:** `rate_type` → `pay_type`; `rate_amount` → `rate`.

**Deactivation pattern:** No `is_active` boolean. A rate is active when `effective_to` is null and `effective_from <= today`. To deactivate when creating a new rate for the same staff + pay_type, set the old rate's `effective_to = new_effective_from - 1 day`.

### PayrollPeriod

| Field | Type | Notes |
|---|---|---|
| `period_start` | DateField | Inclusive |
| `period_end` | DateField | Inclusive |
| `status` | CharField | `draft`, `approved`, `paid` |
| `summary` | JSONField | Keyed by str(staff_id) — see format below |
| `total_payout` | DecimalField | Sum of all staff totals |
| `approved_by` | FK → User (nullable) | Set when status → approved |
| `approved_at` | DateTimeField (nullable) | |
| `notes` | TextField | |

**Summary JSON format:**
```json
{
  "42": {
    "name": "Jane Smith",
    "hours": 40.0,
    "classes": 12,
    "total": 850.00
  }
}
```

---

## Data Sources for Calculation

### Hourly staff
`Shift` model in `apps/checkin/models.py`:
- Filter: `staff=user`, `date__range=(period_start, period_end)`, `attended=True`
- Hours per shift: `(end_time - start_time).seconds / 3600` (using `datetime.combine`)
- Total hours = sum across all matching shifts

### Per-class staff
`ClassSession` model in `apps/scheduling/models.py`:
- Filter: `trainer=user`, `start_datetime__date__range=(period_start, period_end)`, `is_cancelled=False`
- Classes = count of matching sessions

### Salary staff
- Treat `rate` as **monthly** salary amount
- Total = `rate × (period_days / 30)`
- `period_days = (period_end - period_start).days + 1`

---

## Architecture

### File changes

| File | Action |
|---|---|
| `apps/payroll/views.py` | Build all views + `_calculate_payroll` helper |
| `apps/payroll/urls.py` | Define all URL patterns |
| `apps/gym_owner/urls.py` | Add `include('apps.payroll.urls')` at `payroll/` |
| `config/urls.py` | No change needed (payroll routed via gym_owner) |
| 5 templates | Create in `templates/gym_owner/` |

### Auth pattern
Use a `_owner_required` decorator (same pattern as `apps/shop/views.py`) — checks `request.user.role in ('gym_owner', 'platform_admin')`.

---

## Views

### 1. `period_list` — GET + POST `/owner/payroll/`

**GET:** Render list of all `PayrollPeriod` objects ordered by `-period_end`. Include a Generate form with `period_start` and `period_end` date inputs.

**POST (Generate):**
1. Validate `period_start <= period_end`.
2. Create `PayrollPeriod(period_start, period_end, status='draft')`.
3. Call `_calculate_payroll(period)` which populates `summary` and `total_payout`.
4. Save period. Redirect to `payroll:period_detail`.

### 2. `period_detail` — GET `/owner/payroll/<pk>/`

Render the `summary` dict as a table: staff name, hours, classes, rate info, total. Show grand total (`period.total_payout`). Include a "Download CSV" link to `payroll:period_export_csv`.

### 3. `period_export_csv` — GET `/owner/payroll/<pk>/export/`

Returns an `HttpResponse` with `Content-Type: text/csv` and `Content-Disposition: attachment; filename="payroll-<period_start>-<period_end>.csv"`.

Columns: Staff Name, Hours, Classes, Total.

### 4. `rate_list` — GET `/owner/payroll/rates/`

List all `StaffPayRate` records. Group by staff member. Show active rates prominently (effective_to is null), greyed inactive rates below. Include "+ New Rate" button.

### 5. `rate_create` — GET + POST `/owner/payroll/rates/new/`

**POST:**
1. Validate required fields (staff, pay_type, rate, effective_from).
2. Find any existing active rate for same staff + pay_type (effective_to is null).
3. If found, set `effective_to = effective_from - timedelta(days=1)` and save.
4. Create new `StaffPayRate`. Redirect to `payroll:rate_list`.

Form fields: staff select (all is_staff_member users), pay_type select, rate, effective_from, notes.

### 6. `rate_edit` — GET + POST `/owner/payroll/rates/<pk>/edit/`

Edit any field on an existing `StaffPayRate`. Does not trigger deactivation logic (that only applies on create). Redirect to `payroll:rate_list` on success.

### 7. `rate_history` — GET `/owner/payroll/rates/staff/<staff_pk>/`

Show all `StaffPayRate` records for one staff user, ordered by `-effective_from`. Include a back link to `payroll:rate_list`.

---

## `_calculate_payroll(period)` Helper

```python
def _calculate_payroll(period):
    from datetime import datetime, timedelta
    from decimal import Decimal
    from django.contrib.auth import get_user_model
    from apps.checkin.models import Shift
    from apps.scheduling.models import ClassSession

    User = get_user_model()
    period_days = (period.period_end - period.period_start).days + 1
    summary = {}
    grand_total = Decimal('0.00')

    # Get all staff users who have at least one active pay rate
    staff_ids = StaffPayRate.objects.filter(
        effective_to__isnull=True
    ).values_list('staff_id', flat=True).distinct()

    for user in User.objects.filter(pk__in=staff_ids):
        hours = 0.0
        classes = 0
        total = Decimal('0.00')

        for rate_obj in StaffPayRate.objects.filter(staff=user, effective_to__isnull=True):
            if rate_obj.pay_type == 'hourly':
                shifts = Shift.objects.filter(
                    staff=user,
                    date__range=(period.period_start, period.period_end),
                    attended=True,
                )
                for shift in shifts:
                    start = datetime.combine(shift.date, shift.start_time)
                    end = datetime.combine(shift.date, shift.end_time)
                    hours += (end - start).seconds / 3600
                total += Decimal(str(hours)) * rate_obj.rate

            elif rate_obj.pay_type == 'per_class':
                # Count is scoped to this rate type iteration only
                classes += ClassSession.objects.filter(
                    trainer=user,
                    start_datetime__date__range=(period.period_start, period.period_end),
                    is_cancelled=False,
                ).count()
                total += Decimal(classes) * rate_obj.rate

            elif rate_obj.pay_type == 'salary':
                total += rate_obj.rate * Decimal(str(period_days / 30))

        summary[str(user.pk)] = {
            'name': user.get_full_name() or user.username,
            'hours': round(hours, 2),
            'classes': classes,
            'total': float(round(total, 2)),
        }
        grand_total += total

    period.summary = summary
    period.total_payout = round(grand_total, 2)
    period.save()
```

---

## URL Patterns (`apps/payroll/urls.py`)

```
app_name = 'payroll'

/                          period_list        name='period_list'
/<int:pk>/                 period_detail      name='period_detail'
/<int:pk>/export/          period_export_csv  name='period_export_csv'
/rates/                    rate_list          name='rate_list'
/rates/new/                rate_create        name='rate_create'
/rates/<int:pk>/edit/      rate_edit          name='rate_edit'
/rates/staff/<int:pk>/     rate_history       name='rate_history'
```

Wired into `apps/gym_owner/urls.py`:
```python
path('payroll/', include('apps.payroll.urls')),
```

---

## Templates (5 files in `templates/gym_owner/`)

All extend `base/owner_base.html`. Use existing dark Tailwind patterns (`bg-gray-800`, `rounded-xl`, `accent-btn`, etc.).

| Template | Key elements |
|---|---|
| `payroll_periods.html` | Period list table (start, end, status, staff count, total, link); Generate form (two date inputs, Submit) |
| `payroll_period_detail.html` | Summary table (name, hours, classes, total per staff); grand total row; Download CSV button; status badge |
| `payroll_rates.html` | Rates table grouped by staff; active vs inactive styling; New Rate button; History link per staff |
| `payroll_rate_form.html` | Staff select, pay_type select, rate input, effective_from date, notes textarea; Save button |
| `payroll_rate_history.html` | All rates for one staff member; active badge; effective date range; back link |

---

## Edge Cases

- **Staff with no activity in period** — included in summary with hours=0, classes=0, total=0 if they have an active rate.
- **Staff with multiple pay types** — e.g., hourly + per_class — both rates are processed, totals summed.
- **Period_end before period_start** — validation error shown, no period created.
- **No active rates** — Generate produces an empty summary with total_payout=0.
- **Shift spans midnight** — not handled (assumed shifts are within a single calendar day).

# Payroll Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete `/owner/payroll/` section — pay rate CRUD, payroll period generation with earnings calculation, period detail with CSV export, and pay rate history.

**Architecture:** Function-based views in `apps/payroll/views.py` with a `_owner_required` decorator (matching the shop app pattern). A standalone `_calculate_payroll(period)` helper computes earnings from `Shift` and `ClassSession` records. Five Tailwind templates extend `base/owner_base.html`.

**Tech Stack:** Django 4.x, Python stdlib (`csv`, `datetime`, `decimal`), existing `Shift` (apps/checkin) and `ClassSession` (apps/scheduling) models, `StaffPayRate` + `PayrollPeriod` models already migrated.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `apps/payroll/views.py` | Create (replace empty) | All 7 views + `_calculate_payroll` helper |
| `apps/payroll/urls.py` | Modify (currently empty) | 7 URL patterns, `app_name = 'payroll'` |
| `apps/gym_owner/urls.py` | Modify | Add `path('payroll/', include('apps.payroll.urls'))` |
| `templates/gym_owner/payroll_periods.html` | Create | Period list table + Generate form |
| `templates/gym_owner/payroll_period_detail.html` | Create | Summary table, grand total, CSV button |
| `templates/gym_owner/payroll_rates.html` | Create | Rate list, New Rate button, History links |
| `templates/gym_owner/payroll_rate_form.html` | Create | Create/edit rate form |
| `templates/gym_owner/payroll_rate_history.html` | Create | All rates for one staff member |

---

## Task 1: Wire up URLs

**Files:**
- Modify: `apps/payroll/urls.py`
- Modify: `apps/gym_owner/urls.py`

- [ ] **Step 1: Replace `apps/payroll/urls.py` with full URL patterns**

```python
from django.urls import path
from apps.payroll import views

app_name = 'payroll'

urlpatterns = [
    path('',                                views.period_list,       name='period_list'),
    path('<int:pk>/',                       views.period_detail,     name='period_detail'),
    path('<int:pk>/export/',                views.period_export_csv, name='period_export_csv'),
    path('rates/',                          views.rate_list,         name='rate_list'),
    path('rates/new/',                      views.rate_create,       name='rate_create'),
    path('rates/<int:pk>/edit/',            views.rate_edit,         name='rate_edit'),
    path('rates/staff/<int:staff_pk>/',     views.rate_history,      name='rate_history'),
]
```

- [ ] **Step 2: Add payroll include to `apps/gym_owner/urls.py`**

Open `apps/gym_owner/urls.py`. After the existing shop block, add:

```python
    path('payroll/', include('apps.payroll.urls')),
```

The import at the top already has `include` — verify; add it if missing:
```python
from django.urls import path, include
```

- [ ] **Step 3: Commit**

```bash
git add apps/payroll/urls.py apps/gym_owner/urls.py
git commit -m "feat(payroll): wire up URL routing"
```

---

## Task 2: `_calculate_payroll` helper + core views skeleton

**Files:**
- Create: `apps/payroll/views.py`

- [ ] **Step 1: Write the full `views.py` with auth decorator, helper, and all view stubs**

Replace `apps/payroll/views.py` with:

```python
"""
Payroll views — owner management at /owner/payroll/.

Model field mapping (spec → actual):
  rate_type   → pay_type
  rate_amount → rate
  "deactivate" → set effective_to = new_effective_from - timedelta(days=1)

Shift hours: sum (end_time - start_time) for attended=True shifts in period.
ClassSession count: non-cancelled sessions where trainer=staff in period.
Salary: rate (monthly) × (period_days / 30).
"""
import csv
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.payroll.models import PayrollPeriod, StaffPayRate

User = get_user_model()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _owner_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role not in ('gym_owner', 'platform_admin'):
            return redirect(settings.LOGIN_URL)
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


# ---------------------------------------------------------------------------
# Payroll calculation
# ---------------------------------------------------------------------------

def _calculate_payroll(period):
    """
    Populate period.summary and period.total_payout, then save.

    summary format: {str(staff_id): {name, hours, classes, total}}
    Salary rate is treated as monthly; prorated by period_days / 30.
    """
    from apps.checkin.models import Shift
    from apps.scheduling.models import ClassSession

    period_days = (period.period_end - period.period_start).days + 1
    summary = {}
    grand_total = Decimal('0.00')

    staff_ids = (
        StaffPayRate.objects
        .filter(effective_to__isnull=True)
        .values_list('staff_id', flat=True)
        .distinct()
    )

    for user in User.objects.filter(pk__in=staff_ids).order_by('last_name', 'first_name'):
        hours = 0.0
        classes = 0
        total = Decimal('0.00')

        active_rates = StaffPayRate.objects.filter(staff=user, effective_to__isnull=True)

        for rate_obj in active_rates:
            if rate_obj.pay_type == 'hourly':
                shifts = Shift.objects.filter(
                    staff=user,
                    date__range=(period.period_start, period.period_end),
                    attended=True,
                )
                for shift in shifts:
                    start_dt = datetime.combine(shift.date, shift.start_time)
                    end_dt = datetime.combine(shift.date, shift.end_time)
                    hours += (end_dt - start_dt).seconds / 3600
                total += Decimal(str(round(hours, 4))) * rate_obj.rate

            elif rate_obj.pay_type == 'per_class':
                class_count = ClassSession.objects.filter(
                    trainer=user,
                    start_datetime__date__range=(period.period_start, period.period_end),
                    is_cancelled=False,
                ).count()
                classes += class_count
                total += Decimal(class_count) * rate_obj.rate

            elif rate_obj.pay_type == 'salary':
                total += rate_obj.rate * Decimal(str(period_days)) / Decimal('30')

        total = total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        summary[str(user.pk)] = {
            'name': user.get_full_name() or user.username,
            'hours': round(hours, 2),
            'classes': classes,
            'total': float(total),
        }
        grand_total += total

    period.summary = summary
    period.total_payout = grand_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    period.save()


# ---------------------------------------------------------------------------
# Period views
# ---------------------------------------------------------------------------

@_owner_required
def period_list(request):
    if request.method == 'POST':
        period_start = request.POST.get('period_start', '').strip()
        period_end = request.POST.get('period_end', '').strip()

        if not period_start or not period_end:
            messages.error(request, 'Both start and end dates are required.')
        elif period_start > period_end:
            messages.error(request, 'Period start must be on or before period end.')
        else:
            from django.utils.dateparse import parse_date
            start = parse_date(period_start)
            end = parse_date(period_end)
            period = PayrollPeriod.objects.create(
                period_start=start,
                period_end=end,
                status='draft',
            )
            _calculate_payroll(period)
            messages.success(request, f'Payroll period generated ({start} – {end}).')
            return redirect('payroll:period_detail', pk=period.pk)

    periods = PayrollPeriod.objects.all().order_by('-period_end')
    paginator = Paginator(periods, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'gym_owner/payroll_periods.html', {'page_obj': page_obj})


@_owner_required
def period_detail(request, pk):
    period = get_object_or_404(PayrollPeriod, pk=pk)
    # Convert summary dict to a sorted list for template iteration
    rows = sorted(period.summary.values(), key=lambda r: r['name'])
    return render(request, 'gym_owner/payroll_period_detail.html', {
        'period': period,
        'rows': rows,
    })


@_owner_required
def period_export_csv(request, pk):
    period = get_object_or_404(PayrollPeriod, pk=pk)
    filename = f'payroll-{period.period_start}-{period.period_end}.csv'
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['Staff Name', 'Hours', 'Classes', 'Total'])
    for row in sorted(period.summary.values(), key=lambda r: r['name']):
        writer.writerow([
            row['name'],
            row['hours'],
            row['classes'],
            f"{row['total']:.2f}",
        ])
    writer.writerow([])
    writer.writerow(['Grand Total', '', '', f"{float(period.total_payout):.2f}"])
    return response


# ---------------------------------------------------------------------------
# Pay rate views
# ---------------------------------------------------------------------------

@_owner_required
def rate_list(request):
    rates = (
        StaffPayRate.objects
        .select_related('staff')
        .order_by('staff__last_name', 'staff__first_name', '-effective_from')
    )
    return render(request, 'gym_owner/payroll_rates.html', {'rates': rates})


@_owner_required
def rate_create(request):
    staff_users = User.objects.filter(
        role__in=['gym_owner', 'manager', 'trainer', 'front_desk', 'cleaner', 'nutritionist']
    ).order_by('last_name', 'first_name')

    if request.method == 'POST':
        staff_id = request.POST.get('staff', '').strip()
        pay_type = request.POST.get('pay_type', '').strip()
        rate_val = request.POST.get('rate', '').strip()
        effective_from = request.POST.get('effective_from', '').strip()
        notes = request.POST.get('notes', '').strip()

        errors = []
        if not staff_id:
            errors.append('Staff member is required.')
        if not pay_type:
            errors.append('Pay type is required.')
        if not rate_val:
            errors.append('Rate is required.')
        if not effective_from:
            errors.append('Effective from date is required.')

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            from django.utils.dateparse import parse_date
            eff_from = parse_date(effective_from)
            staff_user = get_object_or_404(User, pk=staff_id)

            # Deactivate any existing active rate for same staff + pay_type
            existing = StaffPayRate.objects.filter(
                staff=staff_user,
                pay_type=pay_type,
                effective_to__isnull=True,
            ).first()
            if existing:
                existing.effective_to = eff_from - timedelta(days=1)
                existing.save(update_fields=['effective_to'])

            StaffPayRate.objects.create(
                staff=staff_user,
                pay_type=pay_type,
                rate=Decimal(rate_val),
                effective_from=eff_from,
                notes=notes,
            )
            messages.success(request, f'Pay rate created for {staff_user.get_full_name()}.')
            return redirect('payroll:rate_list')

    return render(request, 'gym_owner/payroll_rate_form.html', {
        'staff_users': staff_users,
        'pay_type_choices': StaffPayRate.PAY_TYPE_CHOICES,
        'rate_obj': None,
    })


@_owner_required
def rate_edit(request, pk):
    rate_obj = get_object_or_404(StaffPayRate, pk=pk)
    staff_users = User.objects.filter(
        role__in=['gym_owner', 'manager', 'trainer', 'front_desk', 'cleaner', 'nutritionist']
    ).order_by('last_name', 'first_name')

    if request.method == 'POST':
        rate_val = request.POST.get('rate', '').strip()
        effective_from = request.POST.get('effective_from', '').strip()
        notes = request.POST.get('notes', '').strip()

        if not rate_val or not effective_from:
            messages.error(request, 'Rate and effective from date are required.')
        else:
            from django.utils.dateparse import parse_date
            rate_obj.rate = Decimal(rate_val)
            rate_obj.effective_from = parse_date(effective_from)
            rate_obj.notes = notes
            rate_obj.save(update_fields=['rate', 'effective_from', 'notes'])
            messages.success(request, 'Pay rate updated.')
            return redirect('payroll:rate_list')

    return render(request, 'gym_owner/payroll_rate_form.html', {
        'staff_users': staff_users,
        'pay_type_choices': StaffPayRate.PAY_TYPE_CHOICES,
        'rate_obj': rate_obj,
    })


@_owner_required
def rate_history(request, staff_pk):
    staff_user = get_object_or_404(User, pk=staff_pk)
    rates = StaffPayRate.objects.filter(staff=staff_user).order_by('-effective_from')
    return render(request, 'gym_owner/payroll_rate_history.html', {
        'staff_user': staff_user,
        'rates': rates,
    })
```

- [ ] **Step 2: Verify the file saved correctly**

```bash
python -c "import ast; ast.parse(open('apps/payroll/views.py').read()); print('Syntax OK')"
```

Expected output: `Syntax OK`

- [ ] **Step 3: Smoke-test URL resolution**

```bash
python manage.py shell -c "
from django.urls import reverse
print(reverse('payroll:period_list'))
print(reverse('payroll:rate_create'))
print(reverse('payroll:period_detail', args=[1]))
print(reverse('payroll:period_export_csv', args=[1]))
print(reverse('payroll:rate_history', args=[1]))
"
```

Expected output (no exceptions):
```
/owner/payroll/
/owner/payroll/rates/new/
/owner/payroll/1/
/owner/payroll/1/export/
/owner/payroll/rates/staff/1/
```

- [ ] **Step 4: Commit**

```bash
git add apps/payroll/views.py
git commit -m "feat(payroll): implement all views and _calculate_payroll helper"
```

---

## Task 3: Period list + Generate form template

**Files:**
- Create: `templates/gym_owner/payroll_periods.html`

- [ ] **Step 1: Create the template**

```html
{% extends "base/owner_base.html" %}
{% block title %}Payroll Periods{% endblock %}
{% block page_title %}Payroll Periods{% endblock %}

{% block header_actions %}
<a href="{% url 'payroll:rate_list' %}" class="px-4 py-2 rounded-lg text-sm font-semibold bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors">Pay Rates</a>
{% endblock %}

{% block content %}
<div class="space-y-5">

  {% if messages %}
  <div class="space-y-2">
    {% for message in messages %}
    <div class="{% if message.tags == 'error' %}bg-red-900/20 border border-red-700/30{% else %}bg-green-900/20 border border-green-700/30{% endif %} rounded-xl px-4 py-3">
      <p class="text-sm {% if message.tags == 'error' %}text-red-400{% else %}text-green-400{% endif %}">{{ message }}</p>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <!-- Generate form -->
  <div class="bg-gray-800 rounded-xl p-5">
    <p class="text-sm font-semibold text-white mb-4">Generate New Payroll Period</p>
    <form method="post" class="flex flex-wrap items-end gap-4">
      {% csrf_token %}
      <div class="flex flex-col gap-1">
        <label class="text-xs text-gray-400 uppercase tracking-wider">Period Start</label>
        <input type="date" name="period_start" required
               class="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-accent">
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs text-gray-400 uppercase tracking-wider">Period End</label>
        <input type="date" name="period_end" required
               class="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-accent">
      </div>
      <button type="submit" class="accent-btn px-5 py-2 rounded-lg text-sm font-semibold">Generate</button>
    </form>
  </div>

  <!-- Period list -->
  <div class="bg-gray-800 rounded-xl overflow-hidden">
    {% if page_obj.object_list %}
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-gray-700 text-xs text-gray-500 uppercase tracking-wider">
          <th class="text-left px-5 py-3 font-medium">Period</th>
          <th class="text-left px-5 py-3 font-medium">Status</th>
          <th class="text-left px-5 py-3 font-medium">Staff</th>
          <th class="text-left px-5 py-3 font-medium">Total Payout</th>
          <th class="px-5 py-3"></th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-700/50">
        {% for period in page_obj %}
        <tr class="hover:bg-gray-700/20 transition-colors">
          <td class="px-5 py-3">
            <p class="text-white font-medium">{{ period.period_start|date:"d M Y" }} – {{ period.period_end|date:"d M Y" }}</p>
            <p class="text-xs text-gray-500">{{ period.period_start|date:"d M" }} – {{ period.period_end|date:"d M Y" }}</p>
          </td>
          <td class="px-5 py-3">
            <span class="text-xs px-2 py-0.5 rounded-full
              {% if period.status == 'paid' %}bg-green-900/40 text-green-400
              {% elif period.status == 'approved' %}bg-blue-900/40 text-blue-400
              {% else %}bg-yellow-900/40 text-yellow-400{% endif %}">
              {{ period.get_status_display }}
            </span>
          </td>
          <td class="px-5 py-3 text-gray-300">{{ period.staff_count }}</td>
          <td class="px-5 py-3 font-semibold text-white">${{ period.total_payout }}</td>
          <td class="px-5 py-3 text-right">
            <a href="{% url 'payroll:period_detail' period.pk %}" class="text-sm accent-text hover:underline">View →</a>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>

    {% if page_obj.has_other_pages %}
    <div class="border-t border-gray-700 px-5 py-4 flex items-center justify-between">
      <p class="text-xs text-gray-500">Page {{ page_obj.number }} of {{ page_obj.paginator.num_pages }}</p>
      <div class="flex gap-2">
        {% if page_obj.has_previous %}
        <a href="?page={{ page_obj.previous_page_number }}" class="px-3 py-1.5 rounded-lg text-xs text-gray-400 hover:text-white hover:bg-gray-700 transition-colors">← Prev</a>
        {% endif %}
        {% if page_obj.has_next %}
        <a href="?page={{ page_obj.next_page_number }}" class="px-3 py-1.5 rounded-lg text-xs text-gray-400 hover:text-white hover:bg-gray-700 transition-colors">Next →</a>
        {% endif %}
      </div>
    </div>
    {% endif %}

    {% else %}
    <div class="py-14 text-center">
      <p class="text-gray-500 text-sm">No payroll periods yet. Generate one above.</p>
    </div>
    {% endif %}
  </div>

</div>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/gym_owner/payroll_periods.html
git commit -m "feat(payroll): add period list + generate form template"
```

---

## Task 4: Period detail + CSV export templates

**Files:**
- Create: `templates/gym_owner/payroll_period_detail.html`

- [ ] **Step 1: Create the period detail template**

```html
{% extends "base/owner_base.html" %}
{% block title %}Payroll {{ period.period_start }} – {{ period.period_end }}{% endblock %}
{% block page_title %}Payroll Period Detail{% endblock %}

{% block header_actions %}
<div class="flex items-center gap-3">
  <a href="{% url 'payroll:period_list' %}" class="px-4 py-2 rounded-lg text-sm font-semibold bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors">← All Periods</a>
  <a href="{% url 'payroll:period_export_csv' period.pk %}" class="accent-btn px-4 py-2 rounded-lg text-sm font-semibold">Download CSV</a>
</div>
{% endblock %}

{% block content %}
<div class="space-y-5">

  <!-- Period meta -->
  <div class="bg-gray-800 rounded-xl px-5 py-4 flex flex-wrap gap-6">
    <div>
      <p class="text-xs text-gray-500 uppercase tracking-wider">Period</p>
      <p class="text-white font-semibold mt-0.5">{{ period.period_start|date:"d M Y" }} – {{ period.period_end|date:"d M Y" }}</p>
    </div>
    <div>
      <p class="text-xs text-gray-500 uppercase tracking-wider">Status</p>
      <span class="inline-block mt-0.5 text-xs px-2 py-0.5 rounded-full
        {% if period.status == 'paid' %}bg-green-900/40 text-green-400
        {% elif period.status == 'approved' %}bg-blue-900/40 text-blue-400
        {% else %}bg-yellow-900/40 text-yellow-400{% endif %}">
        {{ period.get_status_display }}
      </span>
    </div>
    <div>
      <p class="text-xs text-gray-500 uppercase tracking-wider">Staff Count</p>
      <p class="text-white font-semibold mt-0.5">{{ period.staff_count }}</p>
    </div>
    <div>
      <p class="text-xs text-gray-500 uppercase tracking-wider">Total Payout</p>
      <p class="text-xl font-black accent-text mt-0.5">${{ period.total_payout }}</p>
    </div>
  </div>

  <!-- Summary table -->
  <div class="bg-gray-800 rounded-xl overflow-hidden">
    {% if rows %}
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-gray-700 text-xs text-gray-500 uppercase tracking-wider">
          <th class="text-left px-5 py-3 font-medium">Staff Member</th>
          <th class="text-right px-5 py-3 font-medium">Hours</th>
          <th class="text-right px-5 py-3 font-medium">Classes</th>
          <th class="text-right px-5 py-3 font-medium">Total</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-700/50">
        {% for row in rows %}
        <tr class="hover:bg-gray-700/20 transition-colors">
          <td class="px-5 py-3 text-white font-medium">{{ row.name }}</td>
          <td class="px-5 py-3 text-gray-300 text-right">{{ row.hours }}</td>
          <td class="px-5 py-3 text-gray-300 text-right">{{ row.classes }}</td>
          <td class="px-5 py-3 font-semibold text-white text-right">${{ row.total }}</td>
        </tr>
        {% endfor %}
        <!-- Grand total row -->
        <tr class="border-t-2 border-gray-600 bg-gray-750">
          <td class="px-5 py-3 font-bold text-white" colspan="3">Grand Total</td>
          <td class="px-5 py-3 font-black text-xl accent-text text-right">${{ period.total_payout }}</td>
        </tr>
      </tbody>
    </table>
    {% else %}
    <div class="py-14 text-center">
      <p class="text-gray-500 text-sm">No staff with active pay rates found for this period.</p>
    </div>
    {% endif %}
  </div>

</div>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/gym_owner/payroll_period_detail.html
git commit -m "feat(payroll): add period detail template"
```

---

## Task 5: Pay rate list template

**Files:**
- Create: `templates/gym_owner/payroll_rates.html`

- [ ] **Step 1: Create the rate list template**

```html
{% extends "base/owner_base.html" %}
{% block title %}Pay Rates{% endblock %}
{% block page_title %}Pay Rates{% endblock %}

{% block header_actions %}
<div class="flex items-center gap-3">
  <a href="{% url 'payroll:period_list' %}" class="px-4 py-2 rounded-lg text-sm font-semibold bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors">← Periods</a>
  <a href="{% url 'payroll:rate_create' %}" class="accent-btn px-4 py-2 rounded-lg text-sm font-semibold">+ New Rate</a>
</div>
{% endblock %}

{% block content %}
<div class="space-y-5">

  {% if messages %}
  <div class="space-y-2">
    {% for message in messages %}
    <div class="{% if message.tags == 'error' %}bg-red-900/20 border border-red-700/30{% else %}bg-green-900/20 border border-green-700/30{% endif %} rounded-xl px-4 py-3">
      <p class="text-sm {% if message.tags == 'error' %}text-red-400{% else %}text-green-400{% endif %}">{{ message }}</p>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <div class="bg-gray-800 rounded-xl overflow-hidden">
    {% if rates %}
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-gray-700 text-xs text-gray-500 uppercase tracking-wider">
          <th class="text-left px-5 py-3 font-medium">Staff Member</th>
          <th class="text-left px-5 py-3 font-medium">Pay Type</th>
          <th class="text-left px-5 py-3 font-medium">Rate</th>
          <th class="text-left px-5 py-3 font-medium">Effective From</th>
          <th class="text-left px-5 py-3 font-medium">Status</th>
          <th class="px-5 py-3"></th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-700/50">
        {% for rate in rates %}
        <tr class="hover:bg-gray-700/20 transition-colors {% if not rate.is_current %}opacity-50{% endif %}">
          <td class="px-5 py-3">
            <p class="text-white font-medium">{{ rate.staff.get_full_name }}</p>
            <p class="text-xs text-gray-500">{{ rate.staff.role|capfirst }}</p>
          </td>
          <td class="px-5 py-3 text-gray-300">{{ rate.get_pay_type_display }}</td>
          <td class="px-5 py-3 font-semibold text-white">${{ rate.rate }}</td>
          <td class="px-5 py-3 text-gray-300">{{ rate.effective_from|date:"d M Y" }}</td>
          <td class="px-5 py-3">
            {% if rate.effective_to %}
            <span class="text-xs px-2 py-0.5 rounded-full bg-gray-700 text-gray-400">
              Ended {{ rate.effective_to|date:"d M Y" }}
            </span>
            {% else %}
            <span class="text-xs px-2 py-0.5 rounded-full bg-green-900/40 text-green-400">Active</span>
            {% endif %}
          </td>
          <td class="px-5 py-3 text-right">
            <div class="flex items-center justify-end gap-3">
              <a href="{% url 'payroll:rate_edit' rate.pk %}" class="text-xs accent-text hover:underline">Edit</a>
              <a href="{% url 'payroll:rate_history' rate.staff.pk %}" class="text-xs text-gray-400 hover:text-white transition-colors">History</a>
            </div>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="py-14 text-center">
      <p class="text-gray-500 text-sm">No pay rates configured.</p>
      <a href="{% url 'payroll:rate_create' %}" class="inline-block mt-4 accent-btn px-5 py-2.5 rounded-lg text-sm font-semibold">Create First Rate</a>
    </div>
    {% endif %}
  </div>

</div>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/gym_owner/payroll_rates.html
git commit -m "feat(payroll): add pay rate list template"
```

---

## Task 6: Pay rate form template (create + edit)

**Files:**
- Create: `templates/gym_owner/payroll_rate_form.html`

- [ ] **Step 1: Create the rate form template**

```html
{% extends "base/owner_base.html" %}
{% block title %}{% if rate_obj %}Edit Pay Rate{% else %}New Pay Rate{% endif %}{% endblock %}
{% block page_title %}{% if rate_obj %}Edit Pay Rate{% else %}New Pay Rate{% endif %}{% endblock %}

{% block header_actions %}
<a href="{% url 'payroll:rate_list' %}" class="px-4 py-2 rounded-lg text-sm font-semibold bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors">← Back to Rates</a>
{% endblock %}

{% block content %}
<div class="space-y-5">

  {% if messages %}
  <div class="space-y-2">
    {% for message in messages %}
    <div class="bg-red-900/20 border border-red-700/30 rounded-xl px-4 py-3">
      <p class="text-sm text-red-400">{{ message }}</p>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  {% if not rate_obj %}
  <div class="bg-yellow-900/20 border border-yellow-700/30 rounded-xl px-4 py-3">
    <p class="text-sm text-yellow-400">Creating a new rate for an existing active staff + pay type combination will automatically deactivate the previous rate.</p>
  </div>
  {% endif %}

  <form method="post">
    {% csrf_token %}
    <div class="bg-gray-800 rounded-xl p-6 space-y-5">

      <!-- Staff (only on create) -->
      {% if not rate_obj %}
      <div>
        <label class="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Staff Member *</label>
        <select name="staff" required
                class="w-full bg-gray-700 border border-gray-600 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-accent text-sm">
          <option value="">Select staff member…</option>
          {% for user in staff_users %}
          <option value="{{ user.pk }}">{{ user.get_full_name }} ({{ user.role|capfirst }})</option>
          {% endfor %}
        </select>
      </div>

      <!-- Pay Type (only on create) -->
      <div>
        <label class="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Pay Type *</label>
        <select name="pay_type" required
                class="w-full bg-gray-700 border border-gray-600 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-accent text-sm">
          <option value="">Select pay type…</option>
          {% for value, label in pay_type_choices %}
          <option value="{{ value }}">{{ label }}</option>
          {% endfor %}
        </select>
      </div>
      {% else %}
      <!-- Read-only info on edit -->
      <div class="grid grid-cols-2 gap-5">
        <div>
          <p class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">Staff Member</p>
          <p class="text-white text-sm">{{ rate_obj.staff.get_full_name }}</p>
        </div>
        <div>
          <p class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">Pay Type</p>
          <p class="text-white text-sm">{{ rate_obj.get_pay_type_display }}</p>
        </div>
      </div>
      {% endif %}

      <!-- Rate -->
      <div>
        <label class="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">
          Rate ($) *
          <span class="text-gray-500 normal-case font-normal ml-1">hourly rate / monthly salary / per-class fee</span>
        </label>
        <input type="number" name="rate" required step="0.01" min="0"
               value="{{ rate_obj.rate|default:'' }}"
               class="w-full bg-gray-700 border border-gray-600 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-accent text-sm"
               placeholder="0.00">
      </div>

      <!-- Effective From -->
      <div>
        <label class="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Effective From *</label>
        <input type="date" name="effective_from" required
               value="{{ rate_obj.effective_from|date:'Y-m-d'|default:'' }}"
               class="w-full bg-gray-700 border border-gray-600 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-accent text-sm">
      </div>

      <!-- Notes -->
      <div>
        <label class="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Notes</label>
        <textarea name="notes" rows="2"
                  class="w-full bg-gray-700 border border-gray-600 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-accent text-sm resize-none"
                  placeholder="Optional notes">{{ rate_obj.notes|default:'' }}</textarea>
      </div>

      <div class="pt-2">
        <button type="submit" class="accent-btn px-6 py-3 rounded-xl text-sm font-semibold">Save Rate</button>
      </div>

    </div>
  </form>

</div>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/gym_owner/payroll_rate_form.html
git commit -m "feat(payroll): add pay rate create/edit form template"
```

---

## Task 7: Pay rate history template

**Files:**
- Create: `templates/gym_owner/payroll_rate_history.html`

- [ ] **Step 1: Create the rate history template**

```html
{% extends "base/owner_base.html" %}
{% block title %}Pay Rate History — {{ staff_user.get_full_name }}{% endblock %}
{% block page_title %}Pay Rate History{% endblock %}

{% block header_actions %}
<a href="{% url 'payroll:rate_list' %}" class="px-4 py-2 rounded-lg text-sm font-semibold bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors">← Back to Rates</a>
{% endblock %}

{% block content %}
<div class="space-y-5">

  <!-- Staff header -->
  <div class="bg-gray-800 rounded-xl px-5 py-4">
    <p class="text-white font-semibold">{{ staff_user.get_full_name }}</p>
    <p class="text-xs text-gray-400 mt-0.5">{{ staff_user.role|capfirst }} · {{ staff_user.email }}</p>
  </div>

  <!-- Rate history table -->
  <div class="bg-gray-800 rounded-xl overflow-hidden">
    {% if rates %}
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-gray-700 text-xs text-gray-500 uppercase tracking-wider">
          <th class="text-left px-5 py-3 font-medium">Pay Type</th>
          <th class="text-left px-5 py-3 font-medium">Rate</th>
          <th class="text-left px-5 py-3 font-medium">Effective From</th>
          <th class="text-left px-5 py-3 font-medium">Effective To</th>
          <th class="text-left px-5 py-3 font-medium">Status</th>
          <th class="text-left px-5 py-3 font-medium">Notes</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-700/50">
        {% for rate in rates %}
        <tr class="hover:bg-gray-700/20 transition-colors {% if not rate.is_current %}opacity-60{% endif %}">
          <td class="px-5 py-3 text-gray-300">{{ rate.get_pay_type_display }}</td>
          <td class="px-5 py-3 font-semibold text-white">${{ rate.rate }}</td>
          <td class="px-5 py-3 text-gray-300">{{ rate.effective_from|date:"d M Y" }}</td>
          <td class="px-5 py-3 text-gray-400">
            {% if rate.effective_to %}{{ rate.effective_to|date:"d M Y" }}{% else %}—{% endif %}
          </td>
          <td class="px-5 py-3">
            {% if rate.effective_to %}
            <span class="text-xs px-2 py-0.5 rounded-full bg-gray-700 text-gray-400">Inactive</span>
            {% else %}
            <span class="text-xs px-2 py-0.5 rounded-full bg-green-900/40 text-green-400">Active</span>
            {% endif %}
          </td>
          <td class="px-5 py-3 text-gray-400 text-xs">{{ rate.notes|default:"—" }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="py-14 text-center">
      <p class="text-gray-500 text-sm">No pay rate history for this staff member.</p>
    </div>
    {% endif %}
  </div>

</div>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/gym_owner/payroll_rate_history.html
git commit -m "feat(payroll): add pay rate history template"
```

---

## Task 8: End-to-end smoke test + final commit

- [ ] **Step 1: Check for Django errors**

```bash
python manage.py check --deploy 2>&1 | grep -E "ERROR|WARNING" | head -20
```

Expected: no `ERROR` lines related to payroll.

- [ ] **Step 2: Verify all 7 URL names resolve**

```bash
python manage.py shell -c "
from django.urls import reverse
urls = [
    ('payroll:period_list', []),
    ('payroll:period_detail', [1]),
    ('payroll:period_export_csv', [1]),
    ('payroll:rate_list', []),
    ('payroll:rate_create', []),
    ('payroll:rate_edit', [1]),
    ('payroll:rate_history', [1]),
]
for name, args in urls:
    print(reverse(name, args=args) if args else reverse(name))
print('All URLs OK')
"
```

Expected: 7 URL paths printed followed by `All URLs OK`.

- [ ] **Step 3: Verify templates are found**

```bash
python manage.py shell -c "
from django.template.loader import get_template
for t in [
    'gym_owner/payroll_periods.html',
    'gym_owner/payroll_period_detail.html',
    'gym_owner/payroll_rates.html',
    'gym_owner/payroll_rate_form.html',
    'gym_owner/payroll_rate_history.html',
]:
    get_template(t)
    print(f'OK: {t}')
"
```

Expected: 5 `OK:` lines, no exceptions.

- [ ] **Step 4: Final commit**

```bash
git add -u
git commit -m "feat(payroll): complete Step 42 payroll tracking

- 7 views: period list/detail/csv, rate list/create/edit/history
- _calculate_payroll: hourly from Shift, per_class from ClassSession, salary prorated
- 5 templates extending owner_base.html
- Deactivation via effective_to date on rate create"
```

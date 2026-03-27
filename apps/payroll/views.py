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
from django.utils.dateparse import parse_date

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
                    hours += (end_dt - start_dt).total_seconds() / 3600
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
            start = parse_date(period_start)
            end = parse_date(period_end)
            if start is None or end is None:
                messages.error(request, 'Invalid date format. Use YYYY-MM-DD.')
            else:
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
            eff_from = parse_date(effective_from)
            if eff_from is None:
                messages.error(request, 'Invalid date format. Use YYYY-MM-DD.')
            else:
                try:
                    rate_decimal = Decimal(rate_val)
                except Exception:
                    messages.error(request, 'Invalid rate amount.')
                    return render(request, 'gym_owner/payroll_rate_form.html', {
                        'staff_users': staff_users,
                        'pay_type_choices': StaffPayRate.PAY_TYPE_CHOICES,
                        'rate_obj': None,
                    })

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
                    rate=rate_decimal,
                    effective_from=eff_from,
                    notes=notes,
                )
                messages.success(request, f'Pay rate created for {staff_user.get_full_name()}.')
                return redirect('payroll:rate_list')

    supported_types = {'hourly', 'salary', 'per_class'}
    pay_type_choices = [(v, l) for v, l in StaffPayRate.PAY_TYPE_CHOICES if v in supported_types]
    return render(request, 'gym_owner/payroll_rate_form.html', {
        'staff_users': staff_users,
        'pay_type_choices': pay_type_choices,
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
            parsed_date = parse_date(effective_from)
            if parsed_date is None:
                messages.error(request, 'Invalid date format. Use YYYY-MM-DD.')
                return render(request, 'gym_owner/payroll_rate_form.html', {
                    'staff_users': staff_users,
                    'pay_type_choices': StaffPayRate.PAY_TYPE_CHOICES,
                    'rate_obj': rate_obj,
                })
            rate_obj.effective_from = parsed_date
            try:
                rate_decimal = Decimal(rate_val)
            except Exception:
                messages.error(request, 'Invalid rate amount.')
                return render(request, 'gym_owner/payroll_rate_form.html', {
                    'staff_users': staff_users,
                    'pay_type_choices': StaffPayRate.PAY_TYPE_CHOICES,
                    'rate_obj': rate_obj,
                })
            rate_obj.rate = rate_decimal
            rate_obj.notes = notes
            rate_obj.save(update_fields=['rate', 'effective_from', 'notes'])
            messages.success(request, 'Pay rate updated.')
            return redirect('payroll:rate_list')

    supported_types = {'hourly', 'salary', 'per_class'}
    pay_type_choices = [(v, l) for v, l in StaffPayRate.PAY_TYPE_CHOICES if v in supported_types]
    return render(request, 'gym_owner/payroll_rate_form.html', {
        'staff_users': staff_users,
        'pay_type_choices': pay_type_choices,
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

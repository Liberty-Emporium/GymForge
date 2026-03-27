"""
Cleaner portal views — mobile-first.

Location resolution: same Shift-based pattern as manager/front_desk portals.
Tasks: CleaningTask instances assigned to request.user for today.
"""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.checkin.models import CleaningTask, Shift, TaskTemplate
from apps.core.models import Location
from apps.inventory.models import Equipment, MaintenanceTicket, SupplyItem, SupplyRequest


_CLEANER_ROLES = {'cleaner', 'manager', 'gym_owner', 'platform_admin'}

_SHIFT_ORDER = ['morning', 'afternoon', 'evening', 'all']


def _cleaner_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role not in _CLEANER_ROLES:
            return HttpResponseForbidden("Cleaner access required.")
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def _get_location(user) -> Location | None:
    today = date.today()
    shift = (
        Shift.objects
        .filter(staff=user, date=today)
        .select_related('location')
        .order_by('-id')
        .first()
    )
    if shift:
        return shift.location
    shift = (
        Shift.objects
        .filter(staff=user)
        .select_related('location')
        .order_by('-date')
        .first()
    )
    if shift:
        return shift.location
    return Location.objects.filter(is_active=True).first()


def _today_tasks(user):
    """All today's tasks for this cleaner, with template prefetched."""
    return (
        CleaningTask.objects
        .filter(assigned_to=user, shift_date=date.today())
        .select_related('template')
        .order_by('template__shift_type', 'template__priority')
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@_cleaner_required
def dashboard(request):
    location = _get_location(request.user)
    today = date.today()
    tasks = _today_tasks(request.user)

    total = tasks.count()
    done = tasks.filter(completed=True).count()
    progress_pct = int(done / total * 100) if total else 0

    # Group by shift_type for display
    shifts = {}
    for task in tasks:
        s = task.template.shift_type
        shifts.setdefault(s, []).append(task)

    # Ordered list of (shift_label, task_list)
    shift_groups = []
    for key in _SHIFT_ORDER:
        if key in shifts:
            label = dict(TaskTemplate.SHIFT_TYPES).get(key, key.title())
            shift_groups.append((label, shifts[key]))

    return render(request, 'cleaner/dashboard.html', {
        'location': location,
        'today': today,
        'total': total,
        'done': done,
        'progress_pct': progress_pct,
        'shift_groups': shift_groups,
    })


# ---------------------------------------------------------------------------
# Task list (all tasks page)
# ---------------------------------------------------------------------------

@_cleaner_required
def task_list(request):
    tasks = _today_tasks(request.user)
    total = tasks.count()
    done = tasks.filter(completed=True).count()
    progress_pct = int(done / total * 100) if total else 0

    pending = [t for t in tasks if not t.completed]
    completed = [t for t in tasks if t.completed]

    return render(request, 'cleaner/task_list.html', {
        'pending': pending,
        'completed_tasks': completed,
        'total': total,
        'done': done,
        'progress_pct': progress_pct,
        'today': date.today(),
    })


# ---------------------------------------------------------------------------
# Complete a task
# ---------------------------------------------------------------------------

@_cleaner_required
def complete_task(request, task_pk):
    task = get_object_or_404(
        CleaningTask, pk=task_pk, assigned_to=request.user, shift_date=date.today()
    )

    if request.method == 'POST':
        task.completed = True
        task.completed_at = timezone.now()

        photo = request.FILES.get('verification_photo')
        if photo:
            task.verification_photo = photo

        task.save()
        messages.success(request, f"✓ '{task.template.name}' marked complete.")
        return redirect('cleaner:task_list')

    return render(request, 'cleaner/complete_task.html', {'task': task})


# ---------------------------------------------------------------------------
# Fault / equipment reporting
# ---------------------------------------------------------------------------

@_cleaner_required
def report_fault(request):
    location = _get_location(request.user)
    equipment_qs = Equipment.objects.filter(
        location=location, is_active=True
    ).order_by('name') if location else Equipment.objects.none()

    if request.method == 'POST':
        equipment_id = request.POST.get('equipment_id') or None
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        photo = request.FILES.get('photo')

        if not title:
            messages.error(request, "Please enter a brief description of the fault.")
            return render(request, 'cleaner/report_fault.html', {
                'equipment_qs': equipment_qs, 'location': location,
            })

        equipment = None
        if equipment_id:
            equipment = get_object_or_404(Equipment, pk=equipment_id)

        MaintenanceTicket.objects.create(
            location=location,
            equipment=equipment,
            reported_by=request.user,
            title=title,
            description=description,
            photo=photo or None,
            priority='medium',
            status='open',
        )
        messages.success(request, "Fault reported. A manager will be notified.")
        return redirect('cleaner:dashboard')

    return render(request, 'cleaner/report_fault.html', {
        'equipment_qs': equipment_qs,
        'location': location,
    })


# ---------------------------------------------------------------------------
# Supply requests
# ---------------------------------------------------------------------------

@_cleaner_required
def supply_request(request):
    location = _get_location(request.user)
    items = SupplyItem.objects.filter(
        location=location, is_active=True
    ).order_by('category', 'name') if location else SupplyItem.objects.none()

    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        quantity = request.POST.get('quantity', '').strip()
        notes = request.POST.get('notes', '').strip()

        if not item_id or not quantity:
            messages.error(request, "Please select an item and enter a quantity.")
            return render(request, 'cleaner/supply_request.html', {
                'items': items, 'location': location,
            })

        try:
            qty = int(quantity)
            if qty < 1:
                raise ValueError
        except ValueError:
            messages.error(request, "Quantity must be a positive number.")
            return render(request, 'cleaner/supply_request.html', {
                'items': items, 'location': location,
            })

        item = get_object_or_404(SupplyItem, pk=item_id)
        SupplyRequest.objects.create(
            supply_item=item,
            requested_by=request.user,
            quantity=qty,
            notes=notes,
            status='pending',
        )
        messages.success(request, f"Supply request for {item.name} submitted.")
        return redirect('cleaner:dashboard')

    return render(request, 'cleaner/supply_request.html', {
        'items': items,
        'location': location,
    })


# ---------------------------------------------------------------------------
# Shift summary
# ---------------------------------------------------------------------------

@_cleaner_required
def shift_summary(request):
    tasks = _today_tasks(request.user)
    total = tasks.count()
    done = tasks.filter(completed=True).count()
    pending = total - done
    progress_pct = int(done / total * 100) if total else 0
    completed_tasks = [t for t in tasks if t.completed]

    return render(request, 'cleaner/shift_summary.html', {
        'total': total,
        'done': done,
        'pending': pending,
        'progress_pct': progress_pct,
        'completed_tasks': completed_tasks,
        'today': date.today(),
    })

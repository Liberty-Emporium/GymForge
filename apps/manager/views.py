"""
Manager portal views (/manager/).

CRITICAL: Every queryset is scoped to the manager's assigned location.
Managers must not see data from other locations.

Location assignment: derived from today's Shift record; falls back to most
recent shift location; final fallback to first active Location.

All views require role='manager' (or gym_owner / platform_admin).
"""
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.checkin.models import CheckIn, MemberNote, Shift
from apps.core.models import Location
from apps.inventory.models import Equipment, MaintenanceTicket, SupplyItem
from apps.members.models import MemberProfile
from apps.scheduling.models import ClassSession, ClassType


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def _manager_required(view_func):
    ALLOWED = {'manager', 'gym_owner', 'platform_admin'}

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'{settings.LOGIN_URL}?next={request.path}')
        if request.user.role not in ALLOWED:
            return redirect(settings.LOGIN_URL)
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Location resolution — CRITICAL security boundary
# ---------------------------------------------------------------------------

def _get_manager_location(user) -> Location | None:
    """
    Determine the manager's assigned location.

    Priority:
      1. Today's Shift record
      2. Most recent Shift record
      3. First active Location (single-location gyms)
    """
    today = timezone.localdate()

    shift = (
        Shift.objects
        .filter(staff=user, date=today)
        .select_related('location')
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


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@_manager_required
def dashboard(request):
    location = _get_manager_location(request.user)
    today = timezone.localdate()
    now = timezone.now()

    if not location:
        return render(request, 'manager/no_location.html', {})

    # Today's check-in count at this location
    checkin_count = CheckIn.objects.filter(
        location=location,
        checked_in_at__date=today,
    ).count()

    # Currently in gym (checked in today, not yet checked out)
    in_gym_count = CheckIn.objects.filter(
        location=location,
        checked_in_at__date=today,
        checked_out_at__isnull=True,
    ).count()

    # Upcoming classes today at this location
    upcoming_classes = ClassSession.objects.filter(
        location=location,
        start_datetime__date=today,
        start_datetime__gte=now,
        is_cancelled=False,
    ).select_related('class_type', 'trainer').order_by('start_datetime')[:5]

    # Open maintenance tickets at this location
    open_tickets = MaintenanceTicket.objects.filter(
        location=location,
        status__in=['open', 'in_progress', 'pending_parts'],
    ).count()

    # Low stock supply items at this location
    all_supplies = SupplyItem.objects.filter(location=location, is_active=True)
    low_stock_count = sum(1 for s in all_supplies if s.is_low_stock)

    # Staff on shift today at this location
    staff_on_shift = (
        Shift.objects
        .filter(location=location, date=today)
        .select_related('staff')
        .order_by('start_time')
    )

    # Recent check-ins (last 10) for the feed
    recent_checkins = (
        CheckIn.objects
        .filter(location=location, checked_in_at__date=today)
        .select_related('member__user')
        .order_by('-checked_in_at')[:10]
    )

    return render(request, 'manager/dashboard.html', {
        'location': location,
        'today': today,
        'checkin_count': checkin_count,
        'in_gym_count': in_gym_count,
        'upcoming_classes': upcoming_classes,
        'open_tickets': open_tickets,
        'low_stock_count': low_stock_count,
        'staff_on_shift': staff_on_shift,
        'recent_checkins': recent_checkins,
    })


# ---------------------------------------------------------------------------
# Live check-in feed
# ---------------------------------------------------------------------------

@_manager_required
def checkin_feed(request):
    """Today's check-in list with HTMX auto-refresh every 30 seconds."""
    location = _get_manager_location(request.user)
    today = timezone.localdate()

    qs = (
        CheckIn.objects
        .filter(location=location, checked_in_at__date=today)
        .select_related('member__user', 'checked_in_by')
        .order_by('-checked_in_at')
    )

    paginator = Paginator(qs, 30)
    page = paginator.get_page(request.GET.get('page', 1))

    # HTMX partial refresh — return just the rows
    if request.headers.get('HX-Request'):
        return render(request, 'manager/partials/checkin_rows.html', {
            'page': page,
            'location': location,
        })

    return render(request, 'manager/checkin_feed.html', {
        'page': page,
        'location': location,
        'today': today,
    })


# ---------------------------------------------------------------------------
# Class scheduling
# ---------------------------------------------------------------------------

@_manager_required
def schedule(request):
    location = _get_manager_location(request.user)
    today = timezone.localdate()

    # Default to current week
    from datetime import timedelta
    week_offset = int(request.GET.get('week', 0))
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=6)

    sessions = (
        ClassSession.objects
        .filter(
            location=location,
            start_datetime__date__gte=week_start,
            start_datetime__date__lte=week_end,
        )
        .select_related('class_type', 'trainer')
        .order_by('start_datetime')
    )

    return render(request, 'manager/schedule.html', {
        'location': location,
        'sessions': sessions,
        'week_start': week_start,
        'week_end': week_end,
        'week_offset': week_offset,
        'prev_week': week_offset - 1,
        'next_week': week_offset + 1,
        'today': today,
    })


@_manager_required
def class_session_form(request, pk=None):
    """Create or edit a ClassSession at the manager's location."""
    location = _get_manager_location(request.user)

    session = None
    if pk:
        session = get_object_or_404(ClassSession, pk=pk, location=location)

    class_types = ClassType.objects.filter(is_active=True)
    trainers = (
        MemberProfile.__class__  # avoid MemberProfile import collision
        .__mro__  # not needed
    )
    from apps.accounts.models import User
    trainers = User.objects.filter(
        role__in=['trainer', 'manager'],
        is_active=True,
    )

    if request.method == 'POST':
        class_type_id = request.POST.get('class_type')
        trainer_id = request.POST.get('trainer') or None
        start_str = request.POST.get('start_datetime', '')
        end_str = request.POST.get('end_datetime', '')
        capacity = int(request.POST.get('capacity', 20))
        session_notes = request.POST.get('session_notes', '')

        try:
            from django.utils.dateparse import parse_datetime
            start_dt = parse_datetime(start_str)
            end_dt = parse_datetime(end_str)
            class_type = ClassType.objects.get(pk=class_type_id)
            trainer = User.objects.get(pk=trainer_id) if trainer_id else None

            if session:
                session.class_type = class_type
                session.trainer = trainer
                session.start_datetime = start_dt
                session.end_datetime = end_dt
                session.capacity = capacity
                session.session_notes = session_notes
                session.save()
                messages.success(request, 'Class session updated.')
            else:
                ClassSession.objects.create(
                    class_type=class_type,
                    location=location,
                    trainer=trainer,
                    start_datetime=start_dt,
                    end_datetime=end_dt,
                    capacity=capacity,
                    session_notes=session_notes,
                )
                messages.success(request, 'Class session created.')
            return redirect('manager:schedule')
        except Exception as e:
            messages.error(request, f'Error saving session: {e}')

    return render(request, 'manager/class_session_form.html', {
        'session': session,
        'class_types': class_types,
        'trainers': trainers,
        'location': location,
    })


@_manager_required
@require_POST
def class_session_cancel(request, pk):
    """Cancel a class session at this manager's location."""
    location = _get_manager_location(request.user)
    session = get_object_or_404(ClassSession, pk=pk, location=location)
    reason = request.POST.get('cancellation_reason', '').strip() or 'Cancelled by manager'
    session.is_cancelled = True
    session.cancellation_reason = reason
    session.save(update_fields=['is_cancelled', 'cancellation_reason'])
    messages.success(request, f'"{session.class_type.name}" session cancelled.')
    return redirect('manager:schedule')


# ---------------------------------------------------------------------------
# Staff shifts
# ---------------------------------------------------------------------------

@_manager_required
def staff_shifts(request):
    location = _get_manager_location(request.user)
    today = timezone.localdate()
    from datetime import timedelta
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    today_shifts = (
        Shift.objects
        .filter(location=location, date=today)
        .select_related('staff')
        .order_by('start_time')
    )
    week_shifts = (
        Shift.objects
        .filter(location=location, date__gte=week_start, date__lte=week_end)
        .select_related('staff')
        .order_by('date', 'start_time')
    )

    return render(request, 'manager/shifts.html', {
        'location': location,
        'today': today,
        'today_shifts': today_shifts,
        'week_shifts': week_shifts,
    })


@_manager_required
@require_POST
def shift_attendance(request, pk):
    """Mark a shift as attended (True) or absent (False)."""
    location = _get_manager_location(request.user)
    shift = get_object_or_404(Shift, pk=pk, location=location)
    value = request.POST.get('attended')
    shift.attended = True if value == 'true' else False
    shift.save(update_fields=['attended'])
    return HttpResponse(status=204)


# ---------------------------------------------------------------------------
# Maintenance tickets
# ---------------------------------------------------------------------------

@_manager_required
def maintenance(request):
    location = _get_manager_location(request.user)

    tickets = (
        MaintenanceTicket.objects
        .filter(location=location, status__in=['open', 'in_progress', 'pending_parts'])
        .select_related('equipment', 'reported_by', 'assigned_to')
        .order_by('-priority', '-created_at')
    )
    from apps.accounts.models import User
    staff = User.objects.filter(role__in=['manager', 'trainer', 'front_desk', 'cleaner'], is_active=True)
    equipment_list = Equipment.objects.filter(location=location, is_active=True)

    low_stock = [s for s in SupplyItem.objects.filter(location=location, is_active=True) if s.is_low_stock]

    return render(request, 'manager/maintenance.html', {
        'location': location,
        'tickets': tickets,
        'staff': staff,
        'equipment_list': equipment_list,
        'low_stock': low_stock,
        'priorities': MaintenanceTicket.PRIORITY_CHOICES,
        'statuses': MaintenanceTicket.STATUS_CHOICES,
    })


@_manager_required
@require_POST
def ticket_create(request):
    location = _get_manager_location(request.user)
    title = request.POST.get('title', '').strip()
    description = request.POST.get('description', '').strip()
    priority = request.POST.get('priority', 'medium')
    equipment_id = request.POST.get('equipment') or None
    assigned_id = request.POST.get('assigned_to') or None

    if not title:
        messages.error(request, 'Title is required.')
        return redirect('manager:maintenance')

    from apps.accounts.models import User
    equipment = Equipment.objects.filter(pk=equipment_id, location=location).first() if equipment_id else None
    assigned = User.objects.filter(pk=assigned_id).first() if assigned_id else None

    MaintenanceTicket.objects.create(
        location=location,
        equipment=equipment,
        title=title,
        description=description,
        priority=priority,
        assigned_to=assigned,
        reported_by=request.user,
    )
    messages.success(request, 'Ticket created.')
    return redirect('manager:maintenance')


@_manager_required
@require_POST
def ticket_update(request, pk):
    location = _get_manager_location(request.user)
    ticket = get_object_or_404(MaintenanceTicket, pk=pk, location=location)

    new_status = request.POST.get('status', ticket.status)
    assigned_id = request.POST.get('assigned_to') or None
    resolution_notes = request.POST.get('resolution_notes', '').strip()

    ticket.status = new_status
    ticket.resolution_notes = resolution_notes
    if assigned_id:
        from apps.accounts.models import User
        ticket.assigned_to = User.objects.filter(pk=assigned_id).first()
    if new_status in ('resolved', 'closed') and not ticket.resolved_at:
        ticket.resolved_at = timezone.now()
    ticket.save()
    messages.success(request, f'Ticket updated to "{ticket.get_status_display()}".')
    return redirect('manager:maintenance')


# ---------------------------------------------------------------------------
# Member notes
# ---------------------------------------------------------------------------

@_manager_required
def member_notes(request):
    location = _get_manager_location(request.user)

    # Managers can see 'staff' and 'manager' visibility notes at their location
    notes = (
        MemberNote.objects
        .filter(
            member__primary_location=location,
            visibility__in=['staff', 'manager'],
        )
        .select_related('member__user', 'author')
        .order_by('-created_at')
    )

    # Member search for adding a note
    search = request.GET.get('q', '').strip()
    members = MemberProfile.objects.none()
    if search:
        members = (
            MemberProfile.objects
            .filter(
                primary_location=location,
                user__first_name__icontains=search,
            ) | MemberProfile.objects.filter(
                primary_location=location,
                user__last_name__icontains=search,
            ) | MemberProfile.objects.filter(
                primary_location=location,
                user__email__icontains=search,
            )
        ).select_related('user').distinct()[:10]

    paginator = Paginator(notes, 25)
    page = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'manager/member_notes.html', {
        'location': location,
        'page': page,
        'search': search,
        'members': members,
        'visibility_choices': MemberNote.VISIBILITY_CHOICES,
    })


@_manager_required
@require_POST
def member_note_add(request):
    location = _get_manager_location(request.user)
    member_id = request.POST.get('member')
    content = request.POST.get('content', '').strip()
    visibility = request.POST.get('visibility', 'staff')

    if not content:
        messages.error(request, 'Note content is required.')
        return redirect('manager:member_notes')

    member = get_object_or_404(MemberProfile, pk=member_id, primary_location=location)

    if visibility not in dict(MemberNote.VISIBILITY_CHOICES):
        visibility = 'staff'

    MemberNote.objects.create(
        member=member,
        author=request.user,
        content=content,
        visibility=visibility,
    )
    messages.success(request, f'Note added for {member.full_name}.')
    return redirect('manager:member_notes')

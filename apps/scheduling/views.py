"""
Class booking views for the member portal (/app/classes/).

All views require role='member'. Mounted via apps/members/urls.py so they
sit under the /app/ prefix alongside all other member portal routes.
"""
import datetime
from functools import wraps

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.billing.tasks import charge_no_show_fee
from apps.loyalty.utils import award_loyalty_points
from apps.members.models import MemberProfile
from apps.scheduling.models import Booking, ClassSession, ClassType


# ---------------------------------------------------------------------------
# Auth guard (mirrors _member_required in members/views.py)
# ---------------------------------------------------------------------------

def _member_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'{settings.LOGIN_URL}?next={request.path}')
        if request.user.role != 'member':
            return redirect(settings.LOGIN_URL)
        return view_func(request, *args, **kwargs)
    return wrapper


def _get_member(request):
    return MemberProfile.objects.select_related('user').get(user=request.user)


# ---------------------------------------------------------------------------
# Schedule (weekly calendar)
# ---------------------------------------------------------------------------

@_member_required
def schedule(request):
    """Weekly class schedule. ?week=N offsets by N weeks from current week."""
    member = _get_member(request)

    today = timezone.localdate()
    week_offset = int(request.GET.get('week', 0))
    week_start = today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(weeks=week_offset)
    week_end = week_start + datetime.timedelta(days=6)

    qs = (
        ClassSession.objects
        .filter(
            start_datetime__date__gte=week_start,
            start_datetime__date__lte=week_end,
            is_cancelled=False,
        )
        .select_related('class_type', 'trainer', 'location')
        .order_by('start_datetime')
    )

    # Optional class-type filter
    class_type_id = request.GET.get('class_type')
    if class_type_id:
        qs = qs.filter(class_type_id=class_type_id)

    sessions_list = list(qs)

    # Fetch member's active bookings for this week in one query
    session_ids = [s.id for s in sessions_list]
    member_bookings = {
        b.class_session_id: b
        for b in Booking.objects.filter(
            member=member,
            class_session_id__in=session_ids,
            status__in=['confirmed', 'waitlisted'],
        )
    }

    # Attach member booking to each session and build day groups
    days = []
    for i in range(7):
        day = week_start + datetime.timedelta(days=i)
        day_sessions = [s for s in sessions_list if s.start_datetime.date() == day]
        for s in day_sessions:
            s.member_booking = member_bookings.get(s.id)
        days.append({'date': day, 'sessions': day_sessions, 'is_today': day == today})

    class_types = ClassType.objects.filter(is_active=True)

    return render(request, 'member/classes_schedule.html', {
        'days': days,
        'week_start': week_start,
        'week_end': week_end,
        'week_offset': week_offset,
        'prev_week': week_offset - 1,
        'next_week': week_offset + 1,
        'class_types': class_types,
        'selected_class_type': class_type_id,
        'member': member,
    })


# ---------------------------------------------------------------------------
# Book a class (HTMX POST)
# ---------------------------------------------------------------------------

@_member_required
@require_POST
def book_class(request, session_id):
    """
    Book a ClassSession. Returns an HTMX partial replacing the booking button.

    - If spots remain   → status='confirmed', award loyalty points.
    - If session is full → status='waitlisted', set waitlist_position.
    - Duplicate bookings are silently returned with current booking state.
    """
    member = _get_member(request)
    session = get_object_or_404(ClassSession, pk=session_id, is_cancelled=False)

    existing = Booking.objects.filter(member=member, class_session=session).first()
    if existing:
        return _booking_button_partial(request, session, existing)

    if session.is_full:
        next_pos = (
            Booking.objects.filter(class_session=session, status='waitlisted').count() + 1
        )
        booking = Booking.objects.create(
            member=member,
            class_session=session,
            status='waitlisted',
            waitlist_position=next_pos,
        )
    else:
        booking = Booking.objects.create(
            member=member,
            class_session=session,
            status='confirmed',
        )
        award_loyalty_points(
            member,
            action='class_attended',
            description=f'Booked: {session.class_type.name}',
        )

    return _booking_button_partial(request, session, booking)


# ---------------------------------------------------------------------------
# Cancel booking (HTMX POST)
# ---------------------------------------------------------------------------

@_member_required
@require_POST
def cancel_booking(request, booking_id):
    """
    Cancel a booking.

    - Waitlisted        → status='cancelled' (no fee)
    - Outside window    → status='cancelled'
    - Inside window     → status='late_cancel' + charge_no_show_fee() called
    After freeing a confirmed spot, promote the first waitlisted member.
    """
    member = _get_member(request)
    booking = get_object_or_404(Booking, pk=booking_id, member=member)

    if booking.status not in ('confirmed', 'waitlisted'):
        return HttpResponse(status=400)

    session = booking.class_session
    membership = member.active_membership

    if booking.status == 'waitlisted':
        booking.status = 'cancelled'
        booking.cancelled_at = timezone.now()
        booking.save(update_fields=['status', 'cancelled_at'])
    else:
        inside_window = False
        if membership:
            window_hours = membership.tier.cancellation_window_hours
            cutoff = session.start_datetime - datetime.timedelta(hours=window_hours)
            inside_window = timezone.now() > cutoff

        if inside_window:
            booking.status = 'late_cancel'
            booking.cancelled_at = timezone.now()
            booking.save(update_fields=['status', 'cancelled_at'])
            fee = membership.tier.late_cancel_fee
            if fee and fee > 0:
                charge_no_show_fee(booking, fee, 'late_cancel')
        else:
            booking.status = 'cancelled'
            booking.cancelled_at = timezone.now()
            booking.save(update_fields=['status', 'cancelled_at'])

        _promote_waitlist(session)

    return _booking_button_partial(request, session, None)


def _promote_waitlist(session):
    """Promote the first waitlisted booking to confirmed if a spot opened up."""
    next_booking = (
        Booking.objects
        .filter(class_session=session, status='waitlisted')
        .order_by('waitlist_position', 'booked_at')
        .first()
    )
    if next_booking and not session.is_full:
        next_booking.status = 'confirmed'
        next_booking.waitlist_position = None
        next_booking.save(update_fields=['status', 'waitlist_position'])
        award_loyalty_points(
            next_booking.member,
            action='class_attended',
            description=f'Promoted from waitlist: {session.class_type.name}',
        )


def _booking_button_partial(request, session, booking):
    return render(request, 'member/partials/booking_button.html', {
        'session': session,
        'booking': booking,
    })


# ---------------------------------------------------------------------------
# My Bookings
# ---------------------------------------------------------------------------

@_member_required
def my_bookings(request):
    """Upcoming confirmed/waitlisted bookings and recent past bookings."""
    member = _get_member(request)
    now = timezone.now()

    upcoming = (
        Booking.objects
        .filter(
            member=member,
            class_session__start_datetime__gte=now,
            status__in=['confirmed', 'waitlisted'],
        )
        .select_related('class_session__class_type', 'class_session__location', 'class_session__trainer')
        .order_by('class_session__start_datetime')
    )

    past = (
        Booking.objects
        .filter(member=member, class_session__start_datetime__lt=now)
        .exclude(status='cancelled')
        .select_related('class_session__class_type', 'class_session__location')
        .order_by('-class_session__start_datetime')[:20]
    )

    return render(request, 'member/classes_my_bookings.html', {
        'upcoming': upcoming,
        'past': past,
        'member': member,
    })


# ---------------------------------------------------------------------------
# Class Detail
# ---------------------------------------------------------------------------

@_member_required
def class_detail(request, session_id):
    """Class session detail with trainer bio and booking action."""
    member = _get_member(request)
    session = get_object_or_404(
        ClassSession.objects.select_related('class_type', 'trainer', 'location'),
        pk=session_id,
    )

    trainer_profile = None
    if session.trainer:
        try:
            from apps.checkin.models import TrainerProfile
            trainer_profile = TrainerProfile.objects.get(user=session.trainer)
        except Exception:
            pass

    member_booking = Booking.objects.filter(
        member=member, class_session=session
    ).first()

    return render(request, 'member/class_detail.html', {
        'session': session,
        'trainer_profile': trainer_profile,
        'member_booking': member_booking,
        'member': member,
    })

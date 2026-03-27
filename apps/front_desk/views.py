"""
Front Desk portal views.
Tablet-optimized check-in, member lookup, walk-in registration, card scan,
guest check-in, and checkout. All views require front-desk-or-above role.

Location resolution (same pattern as manager portal):
  1. Today's Shift  →  2. Most recent Shift  →  3. First active Location
"""
import uuid
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.billing.models import MemberMembership, MemberTab, MembershipTier
from apps.checkin.models import CheckIn, MemberCard, Shift
from apps.core.models import Location
from apps.members.models import MemberProfile
from apps.accounts.models import User


_FD_ROLES = {'front_desk', 'manager', 'gym_owner', 'platform_admin'}


def _fd_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role not in _FD_ROLES:
            return HttpResponseForbidden("Front desk access required.")
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


def _member_search_qs(q: str):
    """Return MemberProfile queryset matching name, email, or card number."""
    return MemberProfile.objects.filter(
        Q(user__first_name__icontains=q) |
        Q(user__last_name__icontains=q) |
        Q(user__email__icontains=q)
    ).select_related('user')


# ---------------------------------------------------------------------------
# Dashboard / check-in hub
# ---------------------------------------------------------------------------

@_fd_required
def dashboard(request):
    location = _get_location(request.user)
    today = date.today()

    if location:
        checkin_count = CheckIn.objects.filter(
            location=location,
            checked_in_at__date=today,
        ).count()
        in_gym = CheckIn.objects.filter(
            location=location,
            checked_in_at__date=today,
            checked_out_at__isnull=True,
        ).select_related('member__user').order_by('-checked_in_at')[:20]
        # Guest count stored in session (CheckIn.member is non-nullable)
        today_key = f"guest_count_{location.pk}_{today.isoformat()}"
        guest_count = request.session.get(today_key, 0)
        recent_checkins = CheckIn.objects.filter(
            location=location,
            checked_in_at__date=today,
        ).select_related('member__user').order_by('-checked_in_at')[:10]
    else:
        checkin_count = in_gym = guest_count = recent_checkins = 0

    # Card scan form result (from redirect)
    scan_result = request.session.pop('scan_result', None)

    return render(request, 'front_desk/dashboard.html', {
        'location': location,
        'today': today,
        'checkin_count': checkin_count,
        'in_gym_count': in_gym.count() if location else 0,
        'in_gym': in_gym,
        'guest_count': guest_count,
        'recent_checkins': recent_checkins,
        'scan_result': scan_result,
    })


# ---------------------------------------------------------------------------
# Card / number scan check-in
# ---------------------------------------------------------------------------

@_fd_required
@require_POST
def card_checkin(request):
    """Scan or type a card number (GF-NNNNN) to check in a member."""
    card_number = request.POST.get('card_number', '').strip().upper()
    location = _get_location(request.user)

    if not location:
        messages.error(request, "No location assigned. Contact your manager.")
        return redirect('front_desk:dashboard')

    try:
        card = MemberCard.objects.select_related('member__user').get(
            card_number=card_number
        )
    except MemberCard.DoesNotExist:
        messages.error(request, f"Card '{card_number}' not found.")
        return redirect('front_desk:dashboard')

    if not card.is_active:
        messages.error(request, f"Card {card_number} is deactivated.")
        return redirect('front_desk:dashboard')

    member = card.member
    membership = MemberMembership.objects.filter(member=member).order_by('-start_date').first()

    if not membership:
        messages.error(request, f"{member.full_name} has no membership on record.")
        return redirect('front_desk:dashboard')

    if membership.status == 'suspended':
        messages.error(request, f"{member.full_name}'s account is suspended.")
        return redirect('front_desk:dashboard')

    if not membership.allows_access:
        messages.error(
            request,
            f"{member.full_name}'s membership is {membership.status}. Access denied."
        )
        return redirect('front_desk:dashboard')

    # Check if already checked in today
    existing = CheckIn.objects.filter(
        member=member,
        location=location,
        checked_in_at__date=date.today(),
        checked_out_at__isnull=True,
    ).first()
    if existing:
        messages.warning(request, f"{member.full_name} is already checked in.")
        return redirect('front_desk:dashboard')

    CheckIn.objects.create(
        member=member,
        location=location,
        method='manual',
        checked_in_by=request.user,
    )
    messages.success(request, f"✓ {member.full_name} checked in via card.")
    return redirect('front_desk:dashboard')


# ---------------------------------------------------------------------------
# Manual check-in (search by name/email)
# ---------------------------------------------------------------------------

@_fd_required
def manual_checkin(request):
    location = _get_location(request.user)
    results = []
    query = ''

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'search':
            query = request.POST.get('q', '').strip()
            if query:
                results = _member_search_qs(query)[:20]

        elif action == 'checkin':
            member_id = request.POST.get('member_id')
            member = get_object_or_404(MemberProfile, pk=member_id)

            if not location:
                messages.error(request, "No location assigned.")
                return redirect('front_desk:manual_checkin')

            existing = CheckIn.objects.filter(
                member=member,
                location=location,
                checked_in_at__date=date.today(),
                checked_out_at__isnull=True,
            ).first()
            if existing:
                messages.warning(request, f"{member.full_name} is already checked in.")
            else:
                CheckIn.objects.create(
                    member=member,
                    location=location,
                    method='manual',
                    checked_in_by=request.user,
                )
                messages.success(request, f"✓ {member.full_name} checked in.")
            return redirect('front_desk:dashboard')

    return render(request, 'front_desk/manual_checkin.html', {
        'results': results,
        'query': query,
        'location': location,
    })


# ---------------------------------------------------------------------------
# Member checkout
# ---------------------------------------------------------------------------

@_fd_required
@require_POST
def checkout(request, checkin_pk):
    location = _get_location(request.user)
    ci = get_object_or_404(CheckIn, pk=checkin_pk, location=location)

    if ci.checked_out_at:
        messages.warning(request, "Already checked out.")
    else:
        ci.checked_out_at = timezone.now()
        ci.save(update_fields=['checked_out_at'])
        name = ci.member.full_name if not ci.is_guest else 'Guest'
        messages.success(request, f"✓ {name} checked out ({ci.duration_minutes} min).")

    return redirect('front_desk:dashboard')


# ---------------------------------------------------------------------------
# Guest check-in
# ---------------------------------------------------------------------------

@_fd_required
def guest_checkin(request):
    location = _get_location(request.user)

    if request.method == 'POST':
        if not location:
            messages.error(request, "No location assigned.")
            return redirect('front_desk:guest_checkin')

        # CheckIn.member is non-nullable — track guest count via session
        today_key = f"guest_count_{location.pk}_{date.today().isoformat()}"
        request.session[today_key] = request.session.get(today_key, 0) + 1
        messages.success(request, f"Guest checked in. ({request.session[today_key]} guests today at {location.name})")
        return redirect('front_desk:dashboard')

    return render(request, 'front_desk/guest_checkin.html', {'location': location})


# ---------------------------------------------------------------------------
# Member lookup
# ---------------------------------------------------------------------------

@_fd_required
def member_lookup(request):
    results = []
    query = request.GET.get('q', '').strip()
    if query:
        results = _member_search_qs(query)[:20]

    return render(request, 'front_desk/member_lookup.html', {
        'results': results,
        'query': query,
    })


@_fd_required
def member_detail(request, member_pk):
    member = get_object_or_404(MemberProfile, pk=member_pk)
    membership = MemberMembership.objects.filter(member=member).order_by('-start_date').first()
    tab = getattr(member, 'tab', None)
    upcoming_bookings = member.bookings.filter(
        session__start_datetime__gte=timezone.now(),
        status__in=['confirmed', 'waitlisted'],
    ).select_related('session__class_type').order_by('session__start_datetime')[:5]
    loyalty = getattr(member, 'loyalty_account', None)

    return render(request, 'front_desk/member_detail.html', {
        'member': member,
        'membership': membership,
        'tab': tab,
        'upcoming_bookings': upcoming_bookings,
        'loyalty': loyalty,
    })


# ---------------------------------------------------------------------------
# Walk-in registration
# ---------------------------------------------------------------------------

@_fd_required
def walk_in(request):
    tiers = MembershipTier.objects.filter(is_active=True).order_by('price')
    location = _get_location(request.user)

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        phone = request.POST.get('phone', '').strip()
        tier_id = request.POST.get('tier_id')

        errors = []
        if not first_name:
            errors.append("First name is required.")
        if not email:
            errors.append("Email is required.")
        if User.objects.filter(email=email).exists():
            errors.append("A member with that email already exists.")
        if not tier_id:
            errors.append("Please select a membership tier.")

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'front_desk/walk_in.html', {
                'tiers': tiers, 'location': location,
            })

        tier = get_object_or_404(MembershipTier, pk=tier_id)

        # Create user — username derived from email
        username = email.split('@')[0]
        base = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base}{counter}"
            counter += 1

        temp_password = str(uuid.uuid4())[:12]
        user = User.objects.create_user(
            username=username,
            email=email,
            password=temp_password,
            first_name=first_name,
            last_name=last_name,
            role='member',
        )
        user.phone = phone
        user.save(update_fields=['phone'])

        member = MemberProfile.objects.create(user=user)

        today = date.today()
        if tier.billing_cycle == 'drop_in':
            end_date = today
        elif tier.billing_cycle == 'annual':
            end_date = today + timedelta(days=365)
        else:
            end_date = today + timedelta(days=30)

        MemberMembership.objects.create(
            member=member,
            tier=tier,
            status='active',
            start_date=today,
            end_date=end_date,
        )

        messages.success(
            request,
            f"✓ {first_name} {last_name} registered as a member. "
            f"Temporary password: {temp_password}"
        )

        # Auto check them in if we have a location
        if location:
            CheckIn.objects.create(
                member=member,
                location=location,
                method='manual',
                checked_in_by=request.user,
            )
            messages.success(request, f"✓ {first_name} automatically checked in.")

        return redirect('front_desk:member_detail', member_pk=member.pk)

    return render(request, 'front_desk/walk_in.html', {
        'tiers': tiers,
        'location': location,
    })

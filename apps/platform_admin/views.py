"""
Platform Admin Portal Views (/platform/)
Single-tenant: manages the one gym instance instead of a list of tenants.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import AuditLog


def platform_admin_required(view_func):
    from functools import wraps
    from django.core.exceptions import PermissionDenied

    @wraps(view_func)
    @login_required(login_url='/auth/login/')
    def wrapper(request, *args, **kwargs):
        if request.user.role != 'platform_admin':
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Dashboard — shows the one gym's status
# ---------------------------------------------------------------------------

@platform_admin_required
def dashboard(request):
    from apps.gym.models import GymConfig
    from apps.accounts.models import User

    gym = GymConfig.get()
    user_counts = {
        'total':        User.objects.count(),
        'members':      User.objects.filter(role='member').count(),
        'staff':        User.objects.exclude(role__in=['member', 'platform_admin']).count(),
        'gym_owners':   User.objects.filter(role='gym_owner').count(),
    }
    recent_logs = AuditLog.objects.order_by('-timestamp')[:20]

    return render(request, 'platform/dashboard.html', {
        'gym':         gym,
        'user_counts': user_counts,
        'recent_logs': recent_logs,
    })


# ---------------------------------------------------------------------------
# Gym config management
# ---------------------------------------------------------------------------

@platform_admin_required
def gym_detail(request):
    from apps.gym.models import GymConfig
    gym = GymConfig.get()
    return render(request, 'platform/gym_detail.html', {'gym': gym})


@platform_admin_required
@require_POST
def gym_suspend(request):
    from apps.gym.models import GymConfig
    gym = GymConfig.get()
    if gym:
        gym.suspend()
        AuditLog.log(actor_email=request.user.email, action='suspended gym',
                     ip_address=request.META.get('REMOTE_ADDR'))
        messages.warning(request, 'Gym has been suspended.')
    return redirect('platform_admin:gym_detail')


@platform_admin_required
@require_POST
def gym_reactivate(request):
    from apps.gym.models import GymConfig
    gym = GymConfig.get()
    if gym:
        gym.subscription_status = 'active'
        gym.trial_active = False
        gym.member_app_active = True
        gym.save()
        AuditLog.log(actor_email=request.user.email, action='reactivated gym',
                     ip_address=request.META.get('REMOTE_ADDR'))
        messages.success(request, 'Gym has been reactivated.')
    return redirect('platform_admin:gym_detail')


# ---------------------------------------------------------------------------
# Audit log viewer
# ---------------------------------------------------------------------------

@platform_admin_required
def audit_log(request):
    qs = AuditLog.objects.order_by('-timestamp')

    actor = request.GET.get('actor', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if actor:
        qs = qs.filter(actor_email__icontains=actor)
    if date_from:
        qs = qs.filter(timestamp__date__gte=date_from)
    if date_to:
        qs = qs.filter(timestamp__date__lte=date_to)

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'platform/audit_log.html', {
        'page_obj': page, 'actor': actor,
        'date_from': date_from, 'date_to': date_to,
    })

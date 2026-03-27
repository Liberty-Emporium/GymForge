"""
Platform Admin Portal Views (/platform/)

All views require platform_admin role. GymForge branding is shown here
(platform admins are internal staff, not gym members/owners).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.mixins import PlatformAdminRequiredMixin
from apps.tenants.models import GymDomain, GymTenant

from .models import AuditLog, Plan


# ---------------------------------------------------------------------------
# Role enforcement decorator (function-based equivalent of the mixin)
# ---------------------------------------------------------------------------

def platform_admin_required(view_func):
    """Decorator: user must be authenticated with platform_admin role."""
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
# Dashboard
# ---------------------------------------------------------------------------

@platform_admin_required
def dashboard(request):
    tenants = GymTenant.objects.select_related('plan').order_by('-created_at')

    now = timezone.now()
    stats = {
        'total': tenants.count(),
        'trial': tenants.filter(subscription_status='trial').count(),
        'active': tenants.filter(subscription_status='active').count(),
        'suspended': tenants.filter(subscription_status='suspended').count(),
        'cancelled': tenants.filter(subscription_status='cancelled').count(),
    }

    # Trials expiring in the next 3 days
    expiring_soon = [
        t for t in tenants.filter(trial_active=True)
        if 0 <= t.trial_days_remaining <= 3
    ]

    recent_tenants = tenants[:10]
    recent_logs = AuditLog.objects.order_by('-timestamp')[:10]

    return render(request, 'platform/dashboard.html', {
        'stats': stats,
        'expiring_soon': expiring_soon,
        'recent_tenants': recent_tenants,
        'recent_logs': recent_logs,
    })


# ---------------------------------------------------------------------------
# Tenant list
# ---------------------------------------------------------------------------

@platform_admin_required
def tenant_list(request):
    qs = GymTenant.objects.select_related('plan').order_by('-created_at')

    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()

    if query:
        from django.db.models import Q
        qs = qs.filter(
            Q(gym_name__icontains=query) | Q(owner_email__icontains=query)
        )
    if status:
        qs = qs.filter(subscription_status=status)

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))

    # HTMX partial — return only the table rows
    template = 'platform/tenant_list.html'
    if request.headers.get('HX-Request'):
        template = 'platform/partials/tenant_rows.html'

    return render(request, template, {
        'page_obj': page,
        'query': query,
        'status': status,
        'status_choices': GymTenant.SUBSCRIPTION_STATUSES,
    })


# ---------------------------------------------------------------------------
# Tenant create
# ---------------------------------------------------------------------------

@platform_admin_required
def tenant_create(request):
    plans = Plan.objects.filter(is_active=True).order_by('price_monthly')

    if request.method == 'POST':
        gym_name = request.POST.get('gym_name', '').strip()
        owner_email = request.POST.get('owner_email', '').strip()
        schema_name = request.POST.get('schema_name', '').strip().lower()
        subdomain = request.POST.get('subdomain', '').strip().lower()
        plan_id = request.POST.get('plan_id')

        errors = []
        if not gym_name:
            errors.append('Gym name is required.')
        if not owner_email:
            errors.append('Owner email is required.')
        if not schema_name:
            errors.append('Schema name is required.')
        if not subdomain:
            errors.append('Subdomain is required.')
        if GymTenant.objects.filter(schema_name=schema_name).exists():
            errors.append(f'Schema "{schema_name}" already exists.')

        if errors:
            return render(request, 'platform/tenant_create.html', {
                'errors': errors, 'plans': plans,
                'post': request.POST,
            })

        plan = Plan.objects.filter(pk=plan_id).first() if plan_id else None

        tenant = GymTenant(
            schema_name=schema_name,
            gym_name=gym_name,
            owner_email=owner_email,
            plan=plan,
        )
        tenant.save()  # auto_create_schema=True creates the PostgreSQL schema

        # Primary domain
        from django.conf import settings
        domain_host = f'{subdomain}.{getattr(settings, "BASE_DOMAIN", "localhost")}'
        GymDomain.objects.create(tenant=tenant, domain=domain_host, is_primary=True)

        AuditLog.log(
            actor_email=request.user.email,
            action=f'provisioned new tenant: {gym_name}',
            target_model='GymTenant',
            target_id=tenant.pk,
            ip_address=request.META.get('REMOTE_ADDR'),
        )

        messages.success(request, f'Tenant "{gym_name}" provisioned successfully.')
        return redirect('platform_admin:tenant_detail', pk=tenant.pk)

    return render(request, 'platform/tenant_create.html', {'plans': plans})


# ---------------------------------------------------------------------------
# Tenant detail
# ---------------------------------------------------------------------------

@platform_admin_required
def tenant_detail(request, pk):
    tenant = get_object_or_404(GymTenant, pk=pk)
    domains = tenant.domains.all()
    logs = AuditLog.objects.filter(
        target_model='GymTenant', target_id=pk
    ).order_by('-timestamp')[:20]

    return render(request, 'platform/tenant_detail.html', {
        'tenant': tenant,
        'domains': domains,
        'logs': logs,
        'plans': Plan.objects.filter(is_active=True).order_by('price_monthly'),
    })


# ---------------------------------------------------------------------------
# Tenant quick actions
# ---------------------------------------------------------------------------

@platform_admin_required
@require_POST
def tenant_suspend(request, pk):
    tenant = get_object_or_404(GymTenant, pk=pk)
    tenant.suspend()
    AuditLog.log(
        actor_email=request.user.email,
        action='suspended tenant',
        gym_schema=tenant.schema_name,
        target_model='GymTenant',
        target_id=pk,
        ip_address=request.META.get('REMOTE_ADDR'),
    )
    messages.warning(request, f'"{tenant.gym_name}" has been suspended.')
    return redirect('platform_admin:tenant_detail', pk=pk)


@platform_admin_required
@require_POST
def tenant_cancel(request, pk):
    tenant = get_object_or_404(GymTenant, pk=pk)
    tenant.cancel()
    AuditLog.log(
        actor_email=request.user.email,
        action='cancelled tenant',
        gym_schema=tenant.schema_name,
        target_model='GymTenant',
        target_id=pk,
        ip_address=request.META.get('REMOTE_ADDR'),
    )
    messages.error(request, f'"{tenant.gym_name}" has been cancelled.')
    return redirect('platform_admin:tenant_detail', pk=pk)


@platform_admin_required
@require_POST
def tenant_reactivate(request, pk):
    tenant = get_object_or_404(GymTenant, pk=pk)
    tenant.subscription_status = 'active'
    tenant.trial_active = False
    tenant.member_app_active = True
    tenant.save(update_fields=['subscription_status', 'trial_active', 'member_app_active'])
    AuditLog.log(
        actor_email=request.user.email,
        action='reactivated tenant',
        gym_schema=tenant.schema_name,
        target_model='GymTenant',
        target_id=pk,
        ip_address=request.META.get('REMOTE_ADDR'),
    )
    messages.success(request, f'"{tenant.gym_name}" has been reactivated.')
    return redirect('platform_admin:tenant_detail', pk=pk)


# ---------------------------------------------------------------------------
# Impersonation
# ---------------------------------------------------------------------------

@platform_admin_required
def tenant_impersonate(request, pk):
    """
    Log the impersonation action to AuditLog, then redirect the platform admin
    to the tenant's primary domain so django-tenants serves the tenant context.

    The audit log write is unconditional — happens before any redirect.
    """
    tenant = get_object_or_404(GymTenant, pk=pk)

    AuditLog.log(
        actor_email=request.user.email,
        action=f'impersonated tenant: {tenant.gym_name}',
        gym_schema=tenant.schema_name,
        target_model='GymTenant',
        target_id=pk,
        details={'initiated_from': request.META.get('HTTP_HOST', '')},
        ip_address=request.META.get('REMOTE_ADDR'),
    )

    primary_domain = tenant.domains.filter(is_primary=True).first()
    if primary_domain:
        scheme = 'https' if request.is_secure() else 'http'
        url = f'{scheme}://{primary_domain.domain}/owner/'
        return redirect(url)

    messages.warning(
        request,
        f'"{tenant.gym_name}" has no primary domain configured. '
        'Impersonation redirect unavailable.',
    )
    return redirect('platform_admin:tenant_detail', pk=pk)


# ---------------------------------------------------------------------------
# Audit log viewer
# ---------------------------------------------------------------------------

@platform_admin_required
def audit_log(request):
    qs = AuditLog.objects.order_by('-timestamp')

    schema = request.GET.get('schema', '').strip()
    actor = request.GET.get('actor', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if schema:
        qs = qs.filter(gym_schema__icontains=schema)
    if actor:
        qs = qs.filter(actor_email__icontains=actor)
    if date_from:
        qs = qs.filter(timestamp__date__gte=date_from)
    if date_to:
        qs = qs.filter(timestamp__date__lte=date_to)

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'platform/audit_log.html', {
        'page_obj': page,
        'schema': schema,
        'actor': actor,
        'date_from': date_from,
        'date_to': date_to,
    })


# ---------------------------------------------------------------------------
# Plan management
# ---------------------------------------------------------------------------

@platform_admin_required
def plan_list(request):
    plans = Plan.objects.order_by('price_monthly')
    return render(request, 'platform/plan_list.html', {'plans': plans})


@platform_admin_required
def plan_create(request):
    if request.method == 'POST':
        return _save_plan(request, plan=None)
    return render(request, 'platform/plan_form.html', {'plan': None})


@platform_admin_required
def plan_edit(request, pk):
    plan = get_object_or_404(Plan, pk=pk)
    if request.method == 'POST':
        return _save_plan(request, plan=plan)
    return render(request, 'platform/plan_form.html', {'plan': plan})


@platform_admin_required
@require_POST
def plan_deactivate(request, pk):
    plan = get_object_or_404(Plan, pk=pk)
    plan.is_active = False
    plan.save(update_fields=['is_active'])
    AuditLog.log(
        actor_email=request.user.email,
        action=f'deactivated plan: {plan.name}',
        target_model='Plan',
        target_id=pk,
        ip_address=request.META.get('REMOTE_ADDR'),
    )
    messages.warning(request, f'Plan "{plan.name}" deactivated.')
    return redirect('platform_admin:plan_list')


def _save_plan(request, plan):
    """Shared create/edit logic for Plan."""
    name = request.POST.get('name', '').strip()
    max_members = request.POST.get('max_members', '0')
    max_locations = request.POST.get('max_locations', '0')
    price_monthly = request.POST.get('price_monthly', '0')
    stripe_price_id = request.POST.get('stripe_price_id', '').strip()
    is_active = bool(request.POST.get('is_active'))

    errors = []
    if not name:
        errors.append('Name is required.')
    try:
        max_members = int(max_members)
        max_locations = int(max_locations)
        price_monthly = float(price_monthly)
    except ValueError:
        errors.append('Max members, max locations, and price must be numbers.')

    if errors:
        return render(request, 'platform/plan_form.html', {
            'plan': plan, 'errors': errors, 'post': request.POST,
        })

    if plan is None:
        plan = Plan()
    plan.name = name
    plan.max_members = max_members
    plan.max_locations = max_locations
    plan.price_monthly = price_monthly
    plan.stripe_price_id = stripe_price_id
    plan.is_active = is_active
    plan.save()

    AuditLog.log(
        actor_email=request.user.email,
        action=f'{"created" if not plan.pk else "edited"} plan: {plan.name}',
        target_model='Plan',
        target_id=plan.pk,
        ip_address=request.META.get('REMOTE_ADDR'),
    )

    messages.success(request, f'Plan "{plan.name}" saved.')
    return redirect('platform_admin:plan_list')

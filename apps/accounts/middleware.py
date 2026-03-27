from django.shortcuts import redirect
from django.utils import timezone


# Paths that bypass subscription/trial enforcement entirely
EXEMPT_PREFIXES = (
    '/billing/', '/auth/', '/api/', '/platform/',
    '/django-admin/', '/health/', '/setup/',
    '/app/register/', '/app/unavailable/',
)


class GymAccessMiddleware:
    """
    Enforces GymForge trial and subscription rules on every request.

    Logic
    -----
    1. If the request has no tenant (public schema), do nothing.
    2. If the path is exempt (billing, auth, api, platform), do nothing.
    3. If the tenant is on trial and 14+ days have elapsed, expire the trial
       and set subscription_status = 'suspended'.
    4. If the tenant is not active:
       - Gym owners are redirected to the subscribe page.
       - Members are redirected to a "service unavailable" page.
       - Other staff get the same redirect as gym owners.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not hasattr(request, 'tenant'):
            return self.get_response(request)

        if any(request.path.startswith(p) for p in EXEMPT_PREFIXES):
            return self.get_response(request)

        tenant = request.tenant

        # --- Trial expiry check ---
        if tenant.trial_active:
            days_elapsed = (timezone.now() - tenant.trial_start_date).days
            if days_elapsed >= 14:
                tenant.trial_active = False
                tenant.subscription_status = 'suspended'
                tenant.save(update_fields=['trial_active', 'subscription_status'])

        # --- Access enforcement ---
        if not tenant.trial_active and tenant.subscription_status != 'active':
            if not request.user.is_authenticated:
                return self.get_response(request)

            if request.user.role == 'member':
                if not request.path.startswith('/app/unavailable/'):
                    return redirect('/app/unavailable/')

            else:
                # gym_owner and all staff roles
                if not request.path.startswith('/billing/'):
                    return redirect('/billing/subscribe/')

        return self.get_response(request)

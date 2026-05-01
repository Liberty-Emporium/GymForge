from django.shortcuts import redirect
from django.utils import timezone

# Paths that bypass subscription/trial enforcement
EXEMPT_PREFIXES = (
    '/billing/', '/auth/', '/api/',
    '/django-admin/', '/health/', '/setup/',
    '/app/register/', '/app/unavailable/',
)


class GymAccessMiddleware:
    """
    Enforces trial and subscription rules for the single-tenant gym deploy.

    Logic
    -----
    1. If path is exempt, pass through.
    2. If GymConfig doesn't exist yet (pre-setup), pass through.
    3. If trial has elapsed 14+ days, expire it.
    4. If gym is not accessible, redirect based on role.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if any(request.path.startswith(p) for p in EXEMPT_PREFIXES):
            return self.get_response(request)

        from apps.gym.models import GymConfig
        gym = GymConfig.get()

        if gym is None:
            # Setup hasn't been run yet — redirect to setup wizard
            if not request.path.startswith('/setup/'):
                return redirect('/setup/')
            return self.get_response(request)

        # Trial expiry check
        if gym.trial_active:
            days_elapsed = (timezone.now() - gym.trial_start_date).days
            if days_elapsed >= 14:
                gym.trial_active = False
                gym.subscription_status = 'suspended'
                gym.save(update_fields=['trial_active', 'subscription_status'])

        # Access enforcement
        if not gym.is_accessible:
            if not request.user.is_authenticated:
                return self.get_response(request)

            if request.user.role == 'member':
                if not request.path.startswith('/app/unavailable/'):
                    return redirect('/app/unavailable/')
            else:
                if not request.path.startswith('/billing/'):
                    return redirect('/billing/subscribe/')

        return self.get_response(request)

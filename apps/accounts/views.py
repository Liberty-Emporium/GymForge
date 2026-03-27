from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


@login_required
def role_redirect(request):
    """
    Post-login redirect that sends users to their role's portal.
    Used as the LOGIN_REDIRECT_URL target when a role-neutral login page is needed.
    Fully implemented in Step 24 (member onboarding).
    """
    return redirect(request.user.get_portal_url())

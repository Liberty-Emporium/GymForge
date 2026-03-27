from .models import GymProfile


def gym_branding(request):
    """
    Injects gym branding variables into every template context.

    Registered in settings/base.py → TEMPLATES[0]['OPTIONS']['context_processors'].

    Only runs when request.tenant is present AND it's not the public schema.
    Returns an empty dict on the public schema (platform admin, marketing site).

    Variables injected
    ------------------
    gym_name        str   e.g. "Iron House"
    gym_logo_url    str   absolute URL to the gym's logo, or ''
    primary_color   str   hex e.g. "#1a1a2e"
    accent_color    str   hex e.g. "#e94560"
    gym_tagline     str   e.g. "Forge your best self"
    gym_profile     GymProfile instance (full object available in templates)

    Usage in templates
    ------------------
    {{ gym_name }}
    {{ gym_logo_url }}

    In base template <style> block:
        :root {
            --primary: {{ primary_color }};
            --accent:  {{ accent_color }};
        }

    Business rule (Section 17)
    --------------------------
    GymForge branding MUST NOT appear in any member-facing or gym-owner-facing
    template. Use these variables — never hardcode GymForge names or colors.
    """
    # No tenant on the request at all
    if not hasattr(request, 'tenant'):
        return {}

    # Public schema — platform admin, setup wizard, marketing site
    # core.GymProfile only exists in tenant schemas; querying it here raises
    # ProgrammingError ("relation core_gymprofile does not exist").
    try:
        from django_tenants.utils import get_public_schema_name
        if request.tenant.schema_name == get_public_schema_name():
            return {}
    except Exception:
        return {}

    _defaults = {
        'gym_name':     '',
        'gym_logo_url': '',
        'primary_color': '#1a1a2e',
        'accent_color':  '#e94560',
        'gym_tagline':   '',
        'gym_profile':   None,
    }

    try:
        profile = GymProfile.objects.get()
        return {
            'gym_name':     profile.gym_name,
            'gym_logo_url': profile.logo.url if profile.logo else '',
            'primary_color': profile.primary_color,
            'accent_color':  profile.accent_color,
            'gym_tagline':   profile.tagline,
            'gym_profile':   profile,
        }
    except GymProfile.DoesNotExist:
        # Tenant schema exists but provisioning hasn't completed yet
        return _defaults
    except Exception:
        # Defensive catch-all — never break a page over missing branding
        return _defaults

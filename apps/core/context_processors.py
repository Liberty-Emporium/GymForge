"""
Injects gym branding variables into every template context.
Single-tenant: just reads the one GymProfile row directly.
"""
from .models import GymProfile

_DEFAULTS = {
    'gym_name':     '',
    'gym_logo_url': '',
    'primary_color': '#1a1a2e',
    'accent_color':  '#e94560',
    'gym_tagline':   '',
    'gym_profile':   None,
}


def gym_branding(request):
    try:
        profile = GymProfile.objects.first()
        if not profile:
            return _DEFAULTS
        return {
            'gym_name':      profile.gym_name,
            'gym_logo_url':  profile.logo.url if profile.logo else '',
            'primary_color': profile.primary_color,
            'accent_color':  profile.accent_color,
            'gym_tagline':   profile.tagline,
            'gym_profile':   profile,
        }
    except Exception:
        return _DEFAULTS

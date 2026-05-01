"""
Gym landing page — publicly accessible, no login required.
Single-tenant: reads GymProfile directly, no tenant routing needed.
"""
from django.shortcuts import render
from django.http import HttpResponseNotAllowed

DEFAULT_SECTIONS = ['hero', 'about', 'classes', 'trainers', 'pricing', 'contact']


def landing_page(request):
    from apps.core.models import GymProfile, Service, Location
    from apps.gym.models import GymConfig

    # If setup hasn't been run yet, show the GymForge marketing/placeholder page
    gym = GymConfig.get()
    if gym is None:
        return render(request, 'landing/gymforge_home.html')

    try:
        profile = GymProfile.objects.first()
    except Exception:
        profile = None

    if not profile:
        return render(request, 'landing/coming_soon.html', {'profile': None})

    if not profile.landing_page_active:
        return render(request, 'landing/coming_soon.html', {'profile': profile})

    sections_config = profile.landing_page_sections
    if sections_config:
        active_sections = [
            s.get('section', '')
            for s in sections_config
            if isinstance(s, dict) and s.get('section')
        ]
    else:
        active_sections = list(DEFAULT_SECTIONS)

    context = {
        'profile':         profile,
        'active_sections': active_sections,
    }

    if 'about' in active_sections:
        context['services'] = Service.objects.filter(is_active=True)

    if 'classes' in active_sections:
        from apps.scheduling.models import ClassType
        context['class_types'] = ClassType.objects.filter(is_active=True)[:8]

    if 'trainers' in active_sections:
        from apps.checkin.models import TrainerProfile
        context['trainers'] = (
            TrainerProfile.objects
            .filter(is_visible_to_members=True)
            .select_related('user')
        )

    if 'pricing' in active_sections:
        from apps.billing.models import MembershipTier
        context['tiers'] = (
            MembershipTier.objects
            .filter(is_active=True)
            .prefetch_related('included_services')
        )

    if 'contact' in active_sections:
        context['locations'] = (
            Location.objects
            .filter(is_active=True)
            .prefetch_related('hours')
        )

    return render(request, 'landing/landing.html', context)


def submit_lead(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    from apps.leads.models import Lead
    from django.shortcuts import render

    first_name = request.POST.get('first_name', '').strip()
    last_name  = request.POST.get('last_name', '').strip()
    email      = request.POST.get('email', '').strip().lower()
    phone      = request.POST.get('phone', '').strip()

    errors = {}
    if not first_name:
        errors['first_name'] = 'First name is required.'
    if not email and not phone:
        errors['contact'] = 'Please provide an email address or phone number.'
    elif email and '@' not in email:
        errors['email'] = 'Enter a valid email address.'

    if errors:
        return render(request, 'landing/partials/lead_form.html', {
            'errors': errors, 'post': request.POST,
        })

    Lead.objects.create(
        first_name=first_name, last_name=last_name,
        email=email, phone=phone,
        source='website', status='new',
    )
    return render(request, 'landing/partials/lead_success.html', {'first_name': first_name})

"""
Gym provisioning task — sets up the single gym instance.

Single-tenant: no schema_context, no GymTenant/GymDomain.
All data goes into the one database. Creates GymConfig + seeds all tables.
"""
from celery import shared_task

DEFAULT_CLASS_TYPES = [
    ('HIIT',               'High-Intensity Interval Training', 45),
    ('Yoga Flow',          'Mindful movement and flexibility', 60),
    ('Spin',               'High-energy indoor cycling',       45),
    ('Pilates',            'Core strength and flexibility',    55),
    ('Boxing Fit',         'Boxing-inspired cardio workout',   45),
    ('Stretch & Recovery', 'Mobility and recovery session',    30),
]

DEFAULT_LOYALTY_RULES = [
    ('checkin',       10, 1,    'Points awarded on each gym check-in'),
    ('class_attended',20, 1,    'Points awarded for attending a class'),
    ('referral',     100, None, 'Points awarded for referring a new member'),
    ('birthday',      50, None, 'Birthday bonus points'),
]

ALL_PREDEFINED = [
    'Group Fitness Classes', 'Personal Training', 'Nutrition Coaching',
    'Sauna', 'Swimming Pool', 'Yoga', 'Pilates', 'CrossFit',
    'Boxing / Kickboxing', 'Spin / Cycling', 'Stretch & Recovery', 'Open Gym',
]


@shared_task(bind=True)
def provision_gym(self, wizard_data: dict) -> dict:
    """
    Provision the gym in 14 steps. No schema switching needed.
    """
    import re
    from apps.accounts.models import User
    from apps.gym.models import GymConfig

    identity   = wizard_data.get('identity', {})
    locations  = wizard_data.get('locations', [])
    owner_data = wizard_data.get('owner', {})
    plans_data = wizard_data.get('plans', [])
    services   = wizard_data.get('services', {})

    selected_services = services.get('selected', [])
    custom_services   = services.get('custom', [])
    gym_name          = identity.get('gym_name', 'My Gym')
    owner_email       = owner_data.get('email', '')

    # Derive a slug from the gym name
    slug = re.sub(r'[^a-z0-9]+', '-', gym_name.lower()).strip('-')[:50] or 'gym'

    def _p(n, label):
        try:
            self.update_state(state='PROGRESS', meta={'step_num': n, 'step': label})
        except Exception:
            pass

    # Step 1 — GymConfig
    _p(1, 'Creating gym record…')
    gym, _ = GymConfig.objects.get_or_create(
        slug=slug,
        defaults={
            'gym_name':    gym_name,
            'owner_email': owner_email,
            'subscription_status': 'trial',
            'trial_active': True,
            'member_app_active': False,
        }
    )

    # Step 2 — Owner user
    _p(2, 'Creating owner account…')
    if not User.objects.filter(email__iexact=owner_email).exists():
        User.objects.create_user(
            username=owner_email,
            email=owner_email,
            password=owner_data.get('password', ''),
            first_name=owner_data.get('first_name', ''),
            last_name=owner_data.get('last_name', ''),
            role='gym_owner',
            is_active=True,
        )

    # Step 3 — GymProfile (branding)
    _p(3, 'Setting up gym branding…')
    from apps.core.models import GymProfile
    if not GymProfile.objects.exists():
        profile_kwargs = {
            'gym_name':      gym_name,
            'tagline':       identity.get('tagline', ''),
            'primary_color': identity.get('primary_color', '#1a1a2e'),
            'accent_color':  identity.get('accent_color', '#e94560'),
            'landing_page_active': True,
        }
        logo_path = identity.get('logo_path')
        if logo_path:
            profile_kwargs['logo'] = logo_path
        GymProfile.objects.create(**profile_kwargs)

    # Step 4 — Locations + hours
    _p(4, 'Setting up locations…')
    from apps.core.models import Location, LocationHours
    for loc_data in locations:
        loc, created = Location.objects.get_or_create(
            name=loc_data.get('name', 'Main Location'),
            defaults={
                'address':  loc_data.get('address', ''),
                'timezone': loc_data.get('timezone', 'America/New_York'),
            }
        )
        if created:
            hours_data = loc_data.get('hours', {})
            for day in ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']:
                day_info = hours_data.get(day, {})
                LocationHours.objects.create(
                    location=loc, day=day,
                    open_time=day_info.get('open', '06:00') or None,
                    close_time=day_info.get('close', '22:00') or None,
                    is_closed=day_info.get('closed', False),
                )

    # Step 5 — Predefined services
    _p(5, 'Setting up services…')
    from apps.core.models import Service
    service_objs = {}
    for svc_name in ALL_PREDEFINED:
        svc, _ = Service.objects.get_or_create(
            name=svc_name,
            defaults={'is_custom': False, 'is_active': svc_name in selected_services}
        )
        service_objs[svc_name] = svc

    # Step 6 — Custom services
    _p(6, 'Adding custom services…')
    for custom_name in custom_services:
        svc, _ = Service.objects.get_or_create(
            name=custom_name,
            defaults={'is_custom': True, 'is_active': True}
        )
        service_objs[custom_name] = svc

    # Step 7 — Membership tiers
    _p(7, 'Creating membership plans…')
    from apps.billing.models import MembershipTier
    tier_objs = []
    for plan in plans_data:
        try:
            price = float(plan.get('price', 0) or 0)
        except (ValueError, TypeError):
            price = 0.0
        tier, _ = MembershipTier.objects.get_or_create(
            name=plan.get('name', 'Membership'),
            defaults={
                'price':        price,
                'billing_cycle': plan.get('billing_cycle', 'monthly'),
                'description':  plan.get('description', ''),
                'is_active':    True,
            }
        )
        tier_objs.append(tier)

    # Step 8 — Link services to tiers
    _p(8, 'Linking services to plans…')
    active_services = [s for s in service_objs.values() if s.is_active]
    for tier in tier_objs:
        tier.included_services.set(active_services)

    # Step 9 — Default class types
    _p(9, 'Creating default class types…')
    from apps.scheduling.models import ClassType
    for name, description, duration in DEFAULT_CLASS_TYPES:
        ClassType.objects.get_or_create(
            name=name,
            defaults={'description': description, 'duration_minutes': duration, 'is_active': True}
        )

    # Step 10 — Loyalty rules
    _p(10, 'Setting up loyalty programme…')
    from apps.loyalty.models import LoyaltyRule
    for action, points, max_per_day, description in DEFAULT_LOYALTY_RULES:
        LoyaltyRule.objects.get_or_create(
            action=action,
            defaults={'points': points, 'max_per_day': max_per_day, 'is_active': True}
        )

    # Step 11 — Audit log
    _p(11, 'Recording setup event…')
    try:
        from apps.platform_admin.models import AuditLog
        AuditLog.objects.create(
            actor_email='system',
            gym_schema=slug,
            action=f'Gym provisioned: {gym_name}',
            target_model='GymConfig',
            target_id=str(gym.pk),
            details={
                'owner_email': owner_email,
                'locations':   len(locations),
                'plans':       len(plans_data),
                'services':    len(selected_services) + len(custom_services),
            },
        )
    except Exception:
        pass

    # Step 12 — Welcome email
    _p(12, 'Sending welcome email…')
    try:
        from django.core.mail import send_mail
        from django.conf import settings as s
        send_mail(
            subject=f"Welcome to GymForge — {gym_name} is live!",
            message=(
                f"Hi {owner_data.get('first_name', '')},\n\n"
                f"Your gym '{gym_name}' is ready.\n\n"
                f"Log in at: /auth/login/\n\n"
                f"Your 14-day trial starts today.\n\n"
                f"— The GymForge Team"
            ),
            from_email=getattr(s, 'DEFAULT_FROM_EMAIL', 'noreply@gymforge.com'),
            recipient_list=[owner_email],
            fail_silently=True,
        )
    except Exception:
        pass

    return {
        'status':      'ready',
        'slug':        slug,
        'owner_email': owner_email,
        'gym_name':    gym_name,
    }

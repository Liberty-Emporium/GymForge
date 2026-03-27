from django.db import models


class Location(models.Model):
    """
    A physical gym location belonging to the current tenant.

    Every Manager, Trainer, Front Desk, Cleaner, and Nutritionist queryset
    must be filtered by location (Section 17 business rule). This model is
    the anchor for that scoping.
    """

    name = models.CharField(max_length=200)
    address = models.TextField()
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    timezone = models.CharField(max_length=50, default='America/New_York')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Location'
        verbose_name_plural = 'Locations'

    def __str__(self):
        return self.name

    def current_hours(self):
        """Return today's LocationHours row, or None if not set."""
        import datetime
        day_abbr = datetime.date.today().strftime('%a').lower()
        return self.hours.filter(day=day_abbr).first()


class LocationHours(models.Model):
    """Opening hours per day of the week for a Location."""

    DAYS = [
        ('mon', 'Monday'),
        ('tue', 'Tuesday'),
        ('wed', 'Wednesday'),
        ('thu', 'Thursday'),
        ('fri', 'Friday'),
        ('sat', 'Saturday'),
        ('sun', 'Sunday'),
    ]

    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name='hours',
    )
    day = models.CharField(max_length=3, choices=DAYS)
    open_time = models.TimeField(null=True, blank=True)
    close_time = models.TimeField(null=True, blank=True)
    is_closed = models.BooleanField(default=False)

    class Meta:
        ordering = ['location', 'day']
        unique_together = ('location', 'day')
        verbose_name = 'Location Hours'
        verbose_name_plural = 'Location Hours'

    def __str__(self):
        if self.is_closed:
            return f'{self.location.name} — {self.get_day_display()}: Closed'
        return (
            f'{self.location.name} — {self.get_day_display()}: '
            f'{self.open_time} – {self.close_time}'
        )


class Service(models.Model):
    """
    A service offered by the gym (e.g. Classes, Personal Training, Sauna).

    Predefined services are seeded during tenant provisioning (Step 19).
    Gym owners can add custom services via is_custom=True.
    Services are linked to MembershipTiers via a ManyToMany (billing app).
    """

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    # True for gym-owner-added services not in the predefined list
    is_custom = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']
        verbose_name = 'Service'
        verbose_name_plural = 'Services'

    def __str__(self):
        return self.name


class GymProfile(models.Model):
    """
    Singleton per tenant — controls all branding, social links, landing page
    configuration, and gym-wide settings.

    One GymProfile row is created during tenant provisioning (Step 19).
    Always accessed as GymProfile.objects.get() — exactly one per schema.

    Branding rules (Sections 14 + 17)
    -----------------------------------
    - GymForge branding NEVER appears in member-facing or owner-facing views.
    - All member templates use var(--primary) and var(--accent) CSS variables.
    - primary_color and accent_color are injected via the gym_branding
      context processor (apps/core/context_processors.py).
    """

    # ---- Identity ----
    gym_name = models.CharField(max_length=200)
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)
    primary_color = models.CharField(max_length=7, default='#1a1a2e')
    accent_color = models.CharField(max_length=7, default='#e94560')
    tagline = models.CharField(max_length=300, blank=True)
    about_text = models.TextField(blank=True)
    welcome_message = models.TextField(blank=True)

    # ---- Homepage layout ----
    homepage_layout = models.CharField(max_length=50, default='hero')
    banner_image = models.ImageField(upload_to='banners/', blank=True, null=True)

    # ---- Social links ----
    social_instagram = models.URLField(blank=True)
    social_facebook = models.URLField(blank=True)
    social_tiktok = models.URLField(blank=True)
    social_youtube = models.URLField(blank=True)

    # ---- Custom domain ----
    custom_domain = models.CharField(max_length=200, blank=True)
    custom_domain_active = models.BooleanField(default=False)

    # ---- Legal / comms ----
    waiver_text = models.TextField(blank=True)
    email_signature = models.TextField(blank=True)

    # ---- Feature flags ----
    # Dict of feature_key → bool; gym owner toggles features on/off.
    # Example: {"community_feed": true, "shop": false, "challenges": true}
    features_enabled = models.JSONField(default=dict)

    # ---- Landing page ----
    landing_page_active = models.BooleanField(default=True)
    # Ordered list of section configs the gym owner has toggled.
    # Available sections: about, classes, trainers, pricing, contact
    # Example: [{"section": "hero"}, {"section": "classes"}, {"section": "pricing"}]
    landing_page_sections = models.JSONField(default=list)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Gym Profile'
        verbose_name_plural = 'Gym Profile'

    def __str__(self):
        return f'{self.gym_name} — Profile'

    def is_feature_enabled(self, feature_key):
        """Check whether a named feature is enabled for this gym."""
        return bool(self.features_enabled.get(feature_key, True))

    def get_active_social_links(self):
        """Return non-empty social URLs keyed by platform name."""
        links = {
            'instagram': self.social_instagram,
            'facebook': self.social_facebook,
            'tiktok': self.social_tiktok,
            'youtube': self.social_youtube,
        }
        return {k: v for k, v in links.items() if v}

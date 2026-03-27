import uuid

from django.db import models


# ---------------------------------------------------------------------------
# FamilyAccount
# Defined before MemberProfile because MemberProfile has a FK to it.
# ---------------------------------------------------------------------------

class FamilyAccount(models.Model):
    """
    Groups multiple MemberProfile records under a single billing unit.

    Billing rule (Section 17): one Stripe subscription covers all members
    in the family account. Each individual still has their own MemberProfile
    (and RFID card, workout history, health data, etc.).
    """

    primary_member = models.ForeignKey(
        'MemberProfile',
        on_delete=models.CASCADE,
        related_name='family_primary',
    )
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Family Account'
        verbose_name_plural = 'Family Accounts'

    def __str__(self):
        return f'{self.name} (primary: {self.primary_member.user.get_full_name()})'


# ---------------------------------------------------------------------------
# MemberProfile
# ---------------------------------------------------------------------------

def _default_referral_code():
    """Generate a short unique referral code."""
    return uuid.uuid4().hex[:8].upper()


class MemberProfile(models.Model):
    """
    Extends the User model with gym-specific member data.

    One MemberProfile per User where role='member'.
    Created automatically during member registration (Step 24).

    Key relationships
    -----------------
    - MemberCard       (checkin app)   — RFID cards issued to this member
    - MemberMembership (billing app)   — active/historical memberships
    - HealthProfile                    — OneToOne health intake data
    - WorkoutLog                       — session-by-session workout history
    - BodyMetric                       — weight, body fat, measurements over time
    - NutritionRecommendation          — AI-generated meal plans
    - SupplementRecommendation         — AI-generated supplement suggestions
    - MemberAIConversation (ai_coach)  — chat history with the AI coach

    Business rules (Section 17)
    ---------------------------
    - A member can ONLY see their own data — filter at queryset level on every view.
    - referral_code is unique per member; generated once at profile creation.
    """

    user = models.OneToOneField(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='member_profile',
    )
    date_of_birth = models.DateField(null=True, blank=True)
    emergency_contact_name = models.CharField(max_length=200, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    primary_location = models.ForeignKey(
        'core.Location',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='primary_members',
    )
    join_date = models.DateField(auto_now_add=True)

    # Waiver — must be signed before accessing gym facilities (Step 24)
    waiver_signed = models.BooleanField(default=False)
    waiver_signed_at = models.DateTimeField(null=True, blank=True)

    # Loyalty
    loyalty_points = models.IntegerField(default=0)
    referral_code = models.CharField(
        max_length=20,
        unique=True,
        default=_default_referral_code,
    )
    referred_by = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='referrals',
    )

    # Kiosk PIN — hashed with Django's make_password (Step 38)
    pin_hash = models.CharField(max_length=128, blank=True)

    # Firebase Cloud Messaging registration token for push notifications (Step 44)
    fcm_token = models.CharField(max_length=255, blank=True)

    # Family billing
    family_account = models.ForeignKey(
        FamilyAccount,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='members',
    )

    class Meta:
        verbose_name = 'Member Profile'
        verbose_name_plural = 'Member Profiles'

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    @property
    def full_name(self):
        return self.user.get_full_name()

    @property
    def email(self):
        return self.user.email

    @property
    def active_membership(self):
        """Return the single active MemberMembership, or None."""
        return self.memberships.filter(status='active').first()

    @property
    def has_completed_intake(self):
        """True if the AI health intake flow has been completed."""
        try:
            return self.healthprofile.intake_completed
        except HealthProfile.DoesNotExist:
            return False


# ---------------------------------------------------------------------------
# HealthProfile
# ---------------------------------------------------------------------------

class HealthProfile(models.Model):
    """
    Comprehensive health and fitness intake data for the AI coach.

    Populated via the AI health intake conversation flow (Step 26).
    The AI coach system prompt is built from this data (Section 9).

    raw_intake_data stores the full intake JSON as collected from the
    conversation before it is parsed into discrete fields — useful for
    re-running the parser or debugging the intake flow.
    """

    member = models.OneToOneField(
        MemberProfile,
        on_delete=models.CASCADE,
        related_name='healthprofile',
    )

    # ---- Goals ----
    fitness_goal = models.CharField(max_length=100, blank=True)
    goal_detail = models.TextField(blank=True)
    goal_timeline_weeks = models.IntegerField(null=True, blank=True)
    activity_level = models.CharField(max_length=50, blank=True)

    # ---- Health history ----
    injuries_limitations = models.TextField(blank=True)
    medical_conditions = models.TextField(blank=True)
    medications = models.TextField(blank=True)

    # ---- Lifestyle ----
    sleep_hours = models.FloatField(null=True, blank=True)
    stress_level = models.CharField(max_length=20, blank=True)

    # ---- Nutrition ----
    dietary_preference = models.CharField(max_length=50, blank=True)
    food_allergies = models.TextField(blank=True)
    disliked_foods = models.TextField(blank=True)
    current_supplements = models.TextField(blank=True)
    typical_diet_description = models.TextField(blank=True)
    water_intake_liters = models.FloatField(null=True, blank=True)

    # ---- Training preferences ----
    preferred_workout_time = models.CharField(max_length=20, blank=True)
    prefers_group = models.BooleanField(default=False)
    has_worked_with_trainer = models.BooleanField(default=False)
    past_obstacles = models.TextField(blank=True)

    # ---- Intake status ----
    intake_completed = models.BooleanField(default=False)
    raw_intake_data = models.JSONField(default=dict)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Health Profile'
        verbose_name_plural = 'Health Profiles'

    def __str__(self):
        status = 'complete' if self.intake_completed else 'incomplete'
        return f'{self.member.full_name} — Health Profile ({status})'


# ---------------------------------------------------------------------------
# WorkoutLog
# ---------------------------------------------------------------------------

class WorkoutLog(models.Model):
    """
    A single workout session logged by the member.

    source distinguishes AI-recommended plans (tracked for approval flow),
    trainer-assigned plans, and freeform manual entries.

    exercises JSON format (Section 5):
    [
        {
            "name": "Bench Press",
            "sets": [
                {"reps": 10, "weight_kg": 60},
                {"reps": 8,  "weight_kg": 65}
            ]
        }
    ]

    mood_before / energy_after are 1–5 scales used by the AI coach to
    detect overtraining, low energy trends, or plateaus.
    """

    SOURCE_CHOICES = [
        ('ai', 'AI Recommended'),
        ('trainer', 'Trainer Plan'),
        ('manual', 'Manual'),
    ]

    member = models.ForeignKey(
        MemberProfile,
        on_delete=models.CASCADE,
        related_name='workout_logs',
    )
    workout_date = models.DateField()
    logged_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    duration_minutes = models.IntegerField(null=True, blank=True)

    # List of exercise objects — see docstring for format
    exercises = models.JSONField(default=list)

    # Wellness tracking (1–5 scale)
    mood_before = models.IntegerField(null=True, blank=True)
    energy_after = models.IntegerField(null=True, blank=True)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-workout_date', '-logged_at']
        verbose_name = 'Workout Log'
        verbose_name_plural = 'Workout Logs'

    def __str__(self):
        return (
            f'{self.member.full_name} — '
            f'{self.workout_date} ({len(self.exercises)} exercises)'
        )

    @property
    def exercise_count(self):
        return len(self.exercises)

    @property
    def total_sets(self):
        return sum(len(ex.get('sets', [])) for ex in self.exercises)


# ---------------------------------------------------------------------------
# BodyMetric
# ---------------------------------------------------------------------------

class BodyMetric(models.Model):
    """
    A body composition snapshot at a point in time.

    measurements JSON format (Section 5):
    {
        "chest_cm": 100,
        "waist_cm": 80,
        "hips_cm": 95,
        "thigh_cm": 60,
        "arm_cm": 35
    }

    Multiple metrics can be recorded on the same date (e.g. morning weight +
    monthly tape measure). The progress dashboard (Step 30) aggregates these
    via Chart.js to show trend lines.
    """

    member = models.ForeignKey(
        MemberProfile,
        on_delete=models.CASCADE,
        related_name='body_metrics',
    )
    recorded_at = models.DateField()
    weight_kg = models.FloatField(null=True, blank=True)
    body_fat_percent = models.FloatField(null=True, blank=True)
    measurements = models.JSONField(default=dict)

    class Meta:
        ordering = ['-recorded_at']
        verbose_name = 'Body Metric'
        verbose_name_plural = 'Body Metrics'

    def __str__(self):
        parts = []
        if self.weight_kg:
            parts.append(f'{self.weight_kg} kg')
        if self.body_fat_percent:
            parts.append(f'{self.body_fat_percent}% BF')
        detail = ', '.join(parts) or 'measurements only'
        return f'{self.member.full_name} — {self.recorded_at} ({detail})'


# ---------------------------------------------------------------------------
# NutritionRecommendation
# ---------------------------------------------------------------------------

class NutritionRecommendation(models.Model):
    """
    An AI-generated daily nutrition plan for a member.

    Generated by the Member AI Coach using the member's HealthProfile
    (dietary preference, allergies, fitness goal, calorie target).

    meal_plan JSON format (Section 5):
    {
        "breakfast": [{"item": "Oats", "calories": 350, "protein_g": 12}],
        "lunch":     [...],
        "dinner":    [...],
        "snacks":    [...]
    }

    nutritionist_reviewed tracks whether the gym's nutritionist has
    reviewed and signed off on the AI recommendation. Overrides are
    recorded in nutritionist_notes.
    """

    member = models.ForeignKey(
        MemberProfile,
        on_delete=models.CASCADE,
        related_name='nutrition_recommendations',
    )
    generated_at = models.DateTimeField(auto_now_add=True)

    # Macro targets
    daily_calories = models.IntegerField(null=True, blank=True)
    protein_g = models.IntegerField(null=True, blank=True)
    carbs_g = models.IntegerField(null=True, blank=True)
    fat_g = models.IntegerField(null=True, blank=True)

    # Full meal plan
    meal_plan = models.JSONField(default=dict)

    # Nutritionist review
    nutritionist_reviewed = models.BooleanField(default=False)
    nutritionist_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-generated_at']
        verbose_name = 'Nutrition Recommendation'
        verbose_name_plural = 'Nutrition Recommendations'

    def __str__(self):
        reviewed = '✓ reviewed' if self.nutritionist_reviewed else 'pending review'
        return (
            f'{self.member.full_name} — '
            f'{self.generated_at.date()} ({reviewed})'
        )


# ---------------------------------------------------------------------------
# SupplementRecommendation
# ---------------------------------------------------------------------------

class SupplementRecommendation(models.Model):
    """
    An AI-generated supplement suggestion for a member.

    CRITICAL BUSINESS RULE (Section 17 + Section 5)
    ------------------------------------------------
    SUPPLEMENT_DISCLAIMER must ALWAYS be appended in every template that
    displays supplement recommendations. It must NEVER be skipped.
    Store it as a constant and reference it in templates — do not hardcode
    the string in multiple places.

    The AI coach never recommends specific brands — supplement types only
    (e.g. "whey protein" not "Optimum Nutrition Gold Standard").

    professional_override allows the gym's nutritionist to annotate or
    countermand an AI suggestion (e.g. "avoid creatine — member has kidney issue").
    """

    # This constant MUST be appended in every template displaying supplements.
    # Never skip it. Never shorten it. Reference this constant, do not hardcode.
    SUPPLEMENT_DISCLAIMER = (
        "These are general wellness suggestions only. Please consult your doctor "
        "before starting any new supplement, especially if you take medications "
        "or have a medical condition."
    )

    member = models.ForeignKey(
        MemberProfile,
        on_delete=models.CASCADE,
        related_name='supplement_recommendations',
    )
    generated_at = models.DateTimeField(auto_now_add=True)

    # What is being recommended (type only, never a brand)
    supplement_name = models.CharField(max_length=200)
    reason = models.TextField()
    suggested_dosage = models.CharField(max_length=100)
    best_time_to_take = models.CharField(max_length=100)

    # True if the member already takes this supplement (from HealthProfile intake)
    member_already_takes = models.BooleanField(default=False)

    # Nutritionist override
    professional_override = models.TextField(blank=True)
    override_by = models.ForeignKey(
        'accounts.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='supplement_overrides',
    )

    class Meta:
        ordering = ['-generated_at']
        verbose_name = 'Supplement Recommendation'
        verbose_name_plural = 'Supplement Recommendations'

    def __str__(self):
        already = ' (already takes)' if self.member_already_takes else ''
        return f'{self.member.full_name} — {self.supplement_name}{already}'

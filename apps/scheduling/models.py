from django.db import models


# ---------------------------------------------------------------------------
# ClassType
# ---------------------------------------------------------------------------

class ClassType(models.Model):
    """
    A category of group fitness class offered by the gym.

    Examples: "HIIT", "Yoga", "Spin", "Boxing", "Pilates".

    ClassSessions reference a ClassType. Deleting a ClassType is blocked
    if any sessions exist (CASCADE would destroy historical booking data —
    use is_active=False to retire a class type instead).
    """

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    duration_minutes = models.IntegerField(default=60)
    cover_image = models.ImageField(upload_to='classes/', blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Class Type'
        verbose_name_plural = 'Class Types'

    def __str__(self):
        return f'{self.name} ({self.duration_minutes} min)'


# ---------------------------------------------------------------------------
# ClassSession
# ---------------------------------------------------------------------------

class ClassSession(models.Model):
    """
    A single scheduled occurrence of a ClassType.

    One session = one bookable slot on the calendar.
    capacity controls how many confirmed Bookings are allowed before
    new bookings are placed on the waitlist.

    Cancellation sets is_cancelled=True and records a reason. All
    confirmed bookings are notified via the notification system (Step 45).
    """

    class_type = models.ForeignKey(
        ClassType,
        on_delete=models.CASCADE,
        related_name='sessions',
    )
    location = models.ForeignKey(
        'core.Location',
        on_delete=models.CASCADE,
        related_name='class_sessions',
    )
    trainer = models.ForeignKey(
        'accounts.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='class_sessions',
    )
    start_datetime = models.DateTimeField(db_index=True)
    end_datetime = models.DateTimeField()
    capacity = models.IntegerField(default=20)
    is_cancelled = models.BooleanField(default=False)
    cancellation_reason = models.TextField(blank=True)
    session_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['start_datetime']
        verbose_name = 'Class Session'
        verbose_name_plural = 'Class Sessions'

    def __str__(self):
        cancelled = ' [CANCELLED]' if self.is_cancelled else ''
        return (
            f'{self.class_type.name} — '
            f'{self.start_datetime:%a %d %b %Y %H:%M}'
            f'{cancelled}'
        )

    @property
    def confirmed_count(self):
        """Number of confirmed (non-waitlist, non-cancelled) bookings."""
        return self.bookings.filter(status='confirmed').count()

    @property
    def waitlist_count(self):
        return self.bookings.filter(status='waitlisted').count()

    @property
    def spots_remaining(self):
        """Available spots before the session becomes full."""
        return max(self.capacity - self.confirmed_count, 0)

    @property
    def is_full(self):
        return self.spots_remaining == 0


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------

class Booking(models.Model):
    """
    A member's reservation for a ClassSession.

    Status lifecycle
    ----------------
    confirmed   → member has a guaranteed spot
    waitlisted  → session is full; waitlist_position tracks queue order
    cancelled   → member cancelled (may trigger late_cancel fee)
    attended    → marked by trainer/front desk after the class ends
    no_show     → set by the process_no_shows Celery task (Step 43)
    late_cancel → cancelled inside cancellation_window_hours

    No-show / late-cancel fees
    --------------------------
    When status → 'no_show' or 'late_cancel', the process_no_shows task
    checks MembershipTier.no_show_fee / late_cancel_fee and charges
    immediately via Stripe if non-zero. no_show_fee_charged prevents
    double-charging on re-runs.

    Waitlist promotion
    ------------------
    When a confirmed booking is cancelled, the lowest waitlist_position
    booking for that session is promoted to 'confirmed' and the member
    is notified (Step 45).
    """

    STATUS_CHOICES = [
        ('confirmed', 'Confirmed'),
        ('waitlisted', 'Waitlisted'),
        ('cancelled', 'Cancelled'),
        ('attended', 'Attended'),
        ('no_show', 'No Show'),
        ('late_cancel', 'Late Cancel'),
    ]

    member = models.ForeignKey(
        'members.MemberProfile',
        on_delete=models.CASCADE,
        related_name='bookings',
    )
    class_session = models.ForeignKey(
        ClassSession,
        on_delete=models.CASCADE,
        related_name='bookings',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='confirmed',
        db_index=True,
    )
    booked_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    waitlist_position = models.IntegerField(null=True, blank=True)
    no_show_fee_charged = models.BooleanField(default=False)

    class Meta:
        ordering = ['class_session__start_datetime', 'booked_at']
        # A member can only have one booking per session
        unique_together = ('member', 'class_session')
        verbose_name = 'Booking'
        verbose_name_plural = 'Bookings'

    def __str__(self):
        return (
            f'{self.member.full_name} — '
            f'{self.class_session.class_type.name} '
            f'{self.class_session.start_datetime:%d %b %Y %H:%M} '
            f'[{self.status}]'
        )

    @property
    def is_cancellable(self):
        """True if the booking can be cancelled without a late-cancel fee."""
        from django.utils import timezone
        import datetime
        if self.status not in ('confirmed', 'waitlisted'):
            return False
        membership = self.member.active_membership
        if not membership:
            return True
        window_hours = membership.tier.cancellation_window_hours
        cutoff = self.class_session.start_datetime - datetime.timedelta(hours=window_hours)
        return timezone.now() < cutoff


# ---------------------------------------------------------------------------
# Appointment
# ---------------------------------------------------------------------------

class Appointment(models.Model):
    """
    A one-to-one session between a member and a staff member.

    Used for:
    - Personal training sessions (appointment_type='training')
    - Nutrition consultations (appointment_type='nutrition')

    notes_after is filled by the staff member after the session.
    The AI coach can read these notes to improve future recommendations.
    """

    APPOINTMENT_TYPES = [
        ('training', 'Personal Training'),
        ('nutrition', 'Nutrition Consult'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    member = models.ForeignKey(
        'members.MemberProfile',
        on_delete=models.CASCADE,
        related_name='appointments',
    )
    staff = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='appointments',
    )
    appointment_type = models.CharField(max_length=20, choices=APPOINTMENT_TYPES)
    scheduled_at = models.DateTimeField(db_index=True)
    duration_minutes = models.IntegerField(default=60)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True,
    )
    notes_after = models.TextField(blank=True)

    class Meta:
        ordering = ['scheduled_at']
        verbose_name = 'Appointment'
        verbose_name_plural = 'Appointments'

    def __str__(self):
        return (
            f'{self.member.full_name} + {self.staff.get_full_name()} — '
            f'{self.get_appointment_type_display()} '
            f'{self.scheduled_at:%d %b %Y %H:%M} [{self.status}]'
        )


# ---------------------------------------------------------------------------
# WorkoutPlan
# ---------------------------------------------------------------------------

class WorkoutPlan(models.Model):
    """
    A structured workout programme assigned to a member.

    Source distinguishes AI-generated plans (draft, awaiting trainer approval)
    from trainer-created plans (can go straight to active).

    Approval flow for AI-generated plans
    -------------------------------------
    AI generates → status='draft'
    Trainer reviews in trainer portal (Step 34)
    Trainer approves → status='approved', approved_at set
    Member activates → status='active'
    Superseded → status='archived'

    plan_data JSON format (flexible — trainer or AI defines the structure):
    {
        "weeks": [
            {
                "week": 1,
                "days": [
                    {
                        "day": "Monday",
                        "focus": "Upper body",
                        "exercises": [
                            {"name": "Bench Press", "sets": 3, "reps": "8-10", "rest_sec": 90}
                        ]
                    }
                ]
            }
        ]
    }
    """

    SOURCE_CHOICES = [
        ('ai', 'AI Generated'),
        ('trainer', 'Trainer Created'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('approved', 'Trainer Approved'),
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]

    member = models.ForeignKey(
        'members.MemberProfile',
        on_delete=models.CASCADE,
        related_name='workout_plans',
    )
    created_by = models.ForeignKey(
        'accounts.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_workout_plans',
    )
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        db_index=True,
    )
    plan_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Workout Plan'
        verbose_name_plural = 'Workout Plans'

    def __str__(self):
        return (
            f'{self.member.full_name} — '
            f'{self.get_source_display()} plan [{self.status}] '
            f'{self.created_at:%d %b %Y}'
        )

    @property
    def is_editable(self):
        """Only draft plans can be edited."""
        return self.status == 'draft'

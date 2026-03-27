import hashlib
import uuid

from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# MemberCard
# ---------------------------------------------------------------------------

class MemberCard(models.Model):
    """
    An RFID/NFC card issued to a member.

    Security rules (Section 17)
    ---------------------------
    - rfid_token is stored as a SHA-256 hash of a UUID — NEVER plain text.
    - Use generate_token() to produce the value before saving.
    - card_number is a human-readable printed identifier (e.g. GF-00001).
    - Multiple cards can be issued to one member; only is_active=True cards
      grant access.

    One card controls:
    - Gym entry / exit (DoorDevice type='entrance'/'exit')
    - Class studio access (DoorDevice type='studio')
    - Locker bank (DoorDevice type='locker')
    - POS purchases (DoorDevice type='pos')
    - Self-service kiosk (DoorDevice type='kiosk')
    - App login via card tap (scan_type='login')
    """

    member = models.ForeignKey(
        'members.MemberProfile',
        on_delete=models.CASCADE,
        related_name='cards',
    )
    # SHA-256 hash of a UUID — never store or log the raw token
    rfid_token = models.CharField(max_length=100, unique=True)
    # Printed on the physical card, e.g. GF-00001
    card_number = models.CharField(max_length=20, unique=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='issued_cards',
    )
    is_active = models.BooleanField(default=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivation_reason = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['-issued_at']
        verbose_name = 'Member Card'
        verbose_name_plural = 'Member Cards'

    def __str__(self):
        status = 'active' if self.is_active else 'inactive'
        return f'{self.card_number} — {self.member.full_name} [{status}]'

    @staticmethod
    def generate_token():
        """
        Generate a new RFID token: SHA-256 hash of a random UUID.

        Returns a 64-character hex string. Store this value in rfid_token.
        The raw UUID is discarded immediately and never persisted.

        Usage
        -----
        card = MemberCard(
            member=profile,
            rfid_token=MemberCard.generate_token(),
            card_number='GF-00042',
            issued_by=request.user,
        )
        card.save()
        """
        raw = str(uuid.uuid4())
        return hashlib.sha256(raw.encode()).hexdigest()[:64]

    def deactivate(self, reason=''):
        """Deactivate this card. Access is revoked immediately."""
        self.is_active = False
        self.deactivated_at = timezone.now()
        self.deactivation_reason = reason
        self.save(update_fields=['is_active', 'deactivated_at', 'deactivation_reason'])


# ---------------------------------------------------------------------------
# DoorDevice
# ---------------------------------------------------------------------------

class DoorDevice(models.Model):
    """
    A physical device (door reader, POS terminal, kiosk) registered to a location.

    Each device has a unique device_token used by the door agent (Raspberry Pi)
    to authenticate API calls to /api/v1/door/validate/ (Step 32).

    Device types map to scan_type values in CardScanLog for reporting.
    """

    DEVICE_TYPES = [
        ('entrance', 'Main Entrance'),
        ('exit', 'Exit'),
        ('studio', 'Class Studio'),
        ('locker', 'Locker Bank'),
        ('pos', 'Point of Sale'),
        ('kiosk', 'Self-Service Kiosk'),
    ]

    location = models.ForeignKey(
        'core.Location',
        on_delete=models.CASCADE,
        related_name='devices',
    )
    name = models.CharField(max_length=100)
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPES)
    # Auth token sent by the Raspberry Pi on every API call — treat as a secret
    device_token = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['location', 'name']
        verbose_name = 'Door Device'
        verbose_name_plural = 'Door Devices'

    def __str__(self):
        return f'{self.name} ({self.get_device_type_display()}) @ {self.location.name}'

    def mark_seen(self, ip_address=None):
        """Update last_seen timestamp; called by the card validation API."""
        self.last_seen = timezone.now()
        if ip_address:
            self.ip_address = ip_address
        self.save(update_fields=['last_seen', 'ip_address'])


# ---------------------------------------------------------------------------
# CardScanLog — IMMUTABLE
# ---------------------------------------------------------------------------

class CardScanLog(models.Model):
    """
    An immutable record of every RFID card tap across all devices.

    IMMUTABLE — no edit or delete views are ever permitted (Section 17).
    Rows are written once by the card validation API (Step 32) and
    never modified.

    This log is the authoritative source of truth for:
    - Access control audit trail
    - Member check-in history
    - POS purchase initiation records

    result values map to the denial reason shown on the door reader display.
    """

    RESULTS = [
        ('granted', 'Access Granted'),
        ('denied_inactive', 'Denied — Inactive Membership'),
        ('denied_payment', 'Denied — Payment Overdue'),
        ('denied_suspended', 'Denied — Account Suspended'),
        ('denied_hours', 'Denied — Outside Access Hours'),
        ('denied_unknown', 'Denied — Card Not Recognised'),
    ]

    SCAN_TYPES = [
        ('entry', 'Entry'),
        ('exit', 'Exit'),
        ('studio', 'Class Studio'),
        ('locker', 'Locker'),
        ('purchase', 'Purchase'),
        ('kiosk', 'Kiosk Check-In'),
        ('login', 'App Login'),
    ]

    card = models.ForeignKey(
        MemberCard,
        on_delete=models.CASCADE,
        related_name='scan_logs',
    )
    device = models.ForeignKey(
        DoorDevice,
        on_delete=models.CASCADE,
        related_name='scan_logs',
    )
    scanned_at = models.DateTimeField(auto_now_add=True, db_index=True)
    result = models.CharField(max_length=30, choices=RESULTS, db_index=True)
    scan_type = models.CharField(max_length=20, choices=SCAN_TYPES)

    class Meta:
        ordering = ['-scanned_at']
        verbose_name = 'Card Scan Log'
        verbose_name_plural = 'Card Scan Logs'

    def __str__(self):
        return (
            f'{self.scanned_at:%Y-%m-%d %H:%M} '
            f'{self.card.card_number} @ {self.device.name} '
            f'[{self.result}]'
        )


# ---------------------------------------------------------------------------
# LockerAssignment
# ---------------------------------------------------------------------------

class LockerAssignment(models.Model):
    """Maps a member to a physical locker at a location."""

    member = models.ForeignKey(
        'members.MemberProfile',
        on_delete=models.CASCADE,
        related_name='locker_assignments',
    )
    locker_number = models.CharField(max_length=20)
    location = models.ForeignKey(
        'core.Location',
        on_delete=models.CASCADE,
        related_name='locker_assignments',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['location', 'locker_number']
        verbose_name = 'Locker Assignment'
        verbose_name_plural = 'Locker Assignments'

    def __str__(self):
        return (
            f'Locker {self.locker_number} @ {self.location.name} '
            f'— {self.member.full_name}'
        )


# ---------------------------------------------------------------------------
# CheckIn
# ---------------------------------------------------------------------------

class CheckIn(models.Model):
    """
    A member's physical visit to a location.

    Created automatically when an RFID card is tapped at an entrance
    device and access is granted (Step 32). Can also be created manually
    by front desk staff or via the kiosk.

    duration_minutes property requires checked_out_at to be set; the
    front desk or kiosk sets this on exit (Step 35 / Step 38).
    """

    METHOD_CHOICES = [
        ('rfid', 'RFID Card'),
        ('kiosk', 'Kiosk'),
        ('manual', 'Manual'),
        ('app', 'App'),
    ]

    member = models.ForeignKey(
        'members.MemberProfile',
        on_delete=models.CASCADE,
        related_name='checkins',
    )
    location = models.ForeignKey(
        'core.Location',
        on_delete=models.CASCADE,
        related_name='checkins',
    )
    checked_in_at = models.DateTimeField(auto_now_add=True, db_index=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    checked_in_by = models.ForeignKey(
        'accounts.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='manual_checkins',
    )
    is_guest = models.BooleanField(default=False)

    class Meta:
        ordering = ['-checked_in_at']
        verbose_name = 'Check-In'
        verbose_name_plural = 'Check-Ins'

    def __str__(self):
        guest = ' (guest)' if self.is_guest else ''
        return (
            f'{self.member.full_name}{guest} @ {self.location.name} '
            f'{self.checked_in_at:%Y-%m-%d %H:%M}'
        )

    @property
    def duration_minutes(self):
        """Minutes between check-in and check-out. None if still in gym."""
        if self.checked_out_at:
            delta = self.checked_out_at - self.checked_in_at
            return int(delta.total_seconds() / 60)
        return None


# ---------------------------------------------------------------------------
# AccessRule
# ---------------------------------------------------------------------------

class AccessRule(models.Model):
    """
    Controls which membership tiers can access which locations and when.

    Evaluated by the card validation API (Step 32) to decide whether to
    grant or deny a door tap.

    access_start_time / access_end_time = null means 24/7 access.
    days_allowed = [] means access on all days.
    """

    membership_tier = models.ForeignKey(
        'billing.MembershipTier',
        on_delete=models.CASCADE,
        related_name='access_rules',
    )
    location = models.ForeignKey(
        'core.Location',
        on_delete=models.CASCADE,
        related_name='access_rules',
    )
    # null = 24/7 access
    access_start_time = models.TimeField(null=True, blank=True)
    access_end_time = models.TimeField(null=True, blank=True)
    # e.g. ["mon", "tue", "wed", "thu", "fri"] — empty list = all days
    days_allowed = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('membership_tier', 'location')
        verbose_name = 'Access Rule'
        verbose_name_plural = 'Access Rules'

    def __str__(self):
        hours = (
            f'{self.access_start_time}–{self.access_end_time}'
            if self.access_start_time else '24/7'
        )
        return f'{self.membership_tier.name} @ {self.location.name} [{hours}]'


# ---------------------------------------------------------------------------
# Shift
# ---------------------------------------------------------------------------

class Shift(models.Model):
    """A scheduled work shift for a staff member at a location."""

    staff = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='shifts',
    )
    location = models.ForeignKey(
        'core.Location',
        on_delete=models.CASCADE,
        related_name='shifts',
    )
    date = models.DateField(db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    # null = not yet resolved; True/False = confirmed attendance
    attended = models.BooleanField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date', 'start_time']
        verbose_name = 'Shift'
        verbose_name_plural = 'Shifts'

    def __str__(self):
        return (
            f'{self.staff.get_full_name()} @ {self.location.name} '
            f'{self.date} {self.start_time}–{self.end_time}'
        )


# ---------------------------------------------------------------------------
# StaffRequest
# ---------------------------------------------------------------------------

class StaffRequest(models.Model):
    """
    A request submitted by a Manager to add or remove a staff member.

    Approved by the Gym Owner in the owner portal (Step 22).
    """

    REQUEST_TYPES = [
        ('add', 'Add Staff'),
        ('remove', 'Remove Staff'),
    ]

    requested_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='requests_made',
    )
    request_type = models.CharField(max_length=20, choices=REQUEST_TYPES)
    target_email = models.EmailField(blank=True)
    role = models.CharField(max_length=20)
    location = models.ForeignKey(
        'core.Location',
        on_delete=models.CASCADE,
        related_name='staff_requests',
    )
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Staff Request'
        verbose_name_plural = 'Staff Requests'

    def __str__(self):
        return (
            f'{self.get_request_type_display()} {self.target_email} '
            f'as {self.role} [{self.status}]'
        )


# ---------------------------------------------------------------------------
# MemberNote
# ---------------------------------------------------------------------------

class MemberNote(models.Model):
    """
    An internal staff note attached to a member.

    Visibility levels control which staff roles can read the note:
    - 'staff'   → visible to all staff roles
    - 'manager' → visible to manager and above
    - 'owner'   → visible to gym owner only

    Business rule: members NEVER see these notes.
    """

    VISIBILITY_CHOICES = [
        ('staff', 'All Staff'),
        ('manager', 'Manager+'),
        ('owner', 'Owner Only'),
    ]

    member = models.ForeignKey(
        'members.MemberProfile',
        on_delete=models.CASCADE,
        related_name='notes',
    )
    author = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='member_notes',
    )
    content = models.TextField()
    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default='staff',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Member Note'
        verbose_name_plural = 'Member Notes'

    def __str__(self):
        return (
            f'Note on {self.member.full_name} '
            f'by {self.author.get_full_name()} [{self.visibility}]'
        )


# ---------------------------------------------------------------------------
# ClientAssignment
# ---------------------------------------------------------------------------

class ClientAssignment(models.Model):
    """
    Assigns a trainer or nutritionist to a specific member.

    Business rule (Section 17): a trainer can ONLY see members assigned
    via ClientAssignment — enforced in every trainer view queryset.
    """

    ASSIGNMENT_TYPES = [
        ('trainer', 'Trainer'),
        ('nutritionist', 'Nutritionist'),
    ]

    staff = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='client_assignments',
    )
    member = models.ForeignKey(
        'members.MemberProfile',
        on_delete=models.CASCADE,
        related_name='client_assignments',
    )
    assignment_type = models.CharField(max_length=20, choices=ASSIGNMENT_TYPES)
    is_active = models.BooleanField(default=True)
    start_date = models.DateField(auto_now_add=True)

    class Meta:
        unique_together = ('staff', 'member', 'assignment_type')
        ordering = ['-start_date']
        verbose_name = 'Client Assignment'
        verbose_name_plural = 'Client Assignments'

    def __str__(self):
        return (
            f'{self.staff.get_full_name()} → {self.member.full_name} '
            f'[{self.get_assignment_type_display()}]'
        )


# ---------------------------------------------------------------------------
# TaskTemplate
# ---------------------------------------------------------------------------

class TaskTemplate(models.Model):
    """
    A reusable cleaning or maintenance task template for a location.

    Seeded during tenant provisioning (Step 19). The cleaner portal
    (Step 36) generates CleaningTask rows from these templates each shift.
    """

    SHIFT_TYPES = [
        ('morning', 'Morning'),
        ('afternoon', 'Afternoon'),
        ('evening', 'Evening'),
        ('all', 'All Shifts'),
    ]

    location = models.ForeignKey(
        'core.Location',
        on_delete=models.CASCADE,
        related_name='task_templates',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    area = models.CharField(max_length=100)
    priority = models.IntegerField(default=1)
    shift_type = models.CharField(max_length=20, choices=SHIFT_TYPES)

    class Meta:
        ordering = ['location', 'shift_type', 'priority']
        verbose_name = 'Task Template'
        verbose_name_plural = 'Task Templates'

    def __str__(self):
        return f'{self.name} ({self.get_shift_type_display()}) @ {self.location.name}'


# ---------------------------------------------------------------------------
# CleaningTask
# ---------------------------------------------------------------------------

class CleaningTask(models.Model):
    """
    A single cleaning task instance generated from a TaskTemplate.

    Created by a Celery beat task each shift day or on-demand by a manager.
    The cleaner marks tasks complete via the cleaner portal (Step 36)
    and optionally uploads a verification photo.
    """

    template = models.ForeignKey(
        TaskTemplate,
        on_delete=models.CASCADE,
        related_name='tasks',
    )
    assigned_to = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='cleaning_tasks',
    )
    shift_date = models.DateField(db_index=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    verification_photo = models.ImageField(
        upload_to='cleaning/',
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ['-shift_date', 'template__priority']
        verbose_name = 'Cleaning Task'
        verbose_name_plural = 'Cleaning Tasks'

    def __str__(self):
        done = '✓' if self.completed else '○'
        return f'{done} {self.template.name} — {self.assigned_to.get_full_name()} {self.shift_date}'


# ---------------------------------------------------------------------------
# TrainerProfile
# ---------------------------------------------------------------------------

class TrainerProfile(models.Model):
    """
    Extended profile for staff with role='trainer'.

    is_visible_to_members controls whether this trainer appears on the
    gym's public landing page trainer section (Step 21).
    """

    user = models.OneToOneField(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='trainer_profile',
    )
    bio = models.TextField(blank=True)
    specialties = models.CharField(max_length=300, blank=True)
    certifications = models.CharField(max_length=300, blank=True)
    is_visible_to_members = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Trainer Profile'
        verbose_name_plural = 'Trainer Profiles'

    def __str__(self):
        return f'{self.user.get_full_name()} — Trainer'

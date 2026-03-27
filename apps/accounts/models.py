from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    """
    Custom User model for GymForge.

    Extends AbstractUser to add a role field and gym-specific profile fields.
    AUTH_USER_MODEL = 'accounts.User' — must exist before the first migration.

    Roles
    -----
    platform_admin  — GymForge staff; lives in public schema only
    gym_owner       — Subscribing gym owner; one per tenant
    manager         — Location-scoped staff; can manage a single location
    trainer         — Personal trainer; sees only assigned clients
    front_desk      — Reception / check-in; tablet-optimised portal
    cleaner         — Cleaning staff; task checklist + fault reporting
    nutritionist    — Nutrition specialist; meal plans + supplement review
    member          — Gym member; consumer of the member app
    """

    ROLES = [
        ('platform_admin', 'Platform Admin'),
        ('gym_owner', 'Gym Owner'),
        ('manager', 'Manager'),
        ('trainer', 'Trainer'),
        ('front_desk', 'Front Desk'),
        ('cleaner', 'Cleaner'),
        ('nutritionist', 'Nutritionist'),
        ('member', 'Member'),
    ]

    role = models.CharField(
        max_length=20,
        choices=ROLES,
        default='member',
        db_index=True,
    )
    phone = models.CharField(max_length=20, blank=True)
    profile_photo = models.ImageField(
        upload_to='profiles/',
        blank=True,
        null=True,
    )
    # AbstractUser already defines is_active=True; re-declared here per spec
    # and to allow future override (e.g. soft-delete behaviour).
    is_active = models.BooleanField(default=True)

    objects = UserManager()

    class Meta:
        verbose_name = 'user'
        verbose_name_plural = 'users'

    def __str__(self):
        return f'{self.get_full_name()} <{self.email}> [{self.role}]'

    # ------------------------------------------------------------------
    # Convenience role-check properties — use in templates and views
    # ------------------------------------------------------------------

    @property
    def is_platform_admin(self):
        return self.role == 'platform_admin'

    @property
    def is_gym_owner(self):
        return self.role == 'gym_owner'

    @property
    def is_manager(self):
        return self.role == 'manager'

    @property
    def is_trainer(self):
        return self.role == 'trainer'

    @property
    def is_front_desk(self):
        return self.role == 'front_desk'

    @property
    def is_cleaner(self):
        return self.role == 'cleaner'

    @property
    def is_nutritionist(self):
        return self.role == 'nutritionist'

    @property
    def is_member(self):
        return self.role == 'member'

    @property
    def is_staff_member(self):
        """True for any non-member, non-platform-admin user."""
        return self.role not in ('member', 'platform_admin')

    def get_portal_url(self):
        """Return the landing URL for this user's role portal."""
        portal_map = {
            'platform_admin': '/platform/',
            'gym_owner': '/owner/',
            'manager': '/manager/',
            'trainer': '/trainer/',
            'front_desk': '/desk/',
            'cleaner': '/cleaner/',
            'nutritionist': '/nutritionist/',
            'member': '/app/',
        }
        return portal_map.get(self.role, '/')

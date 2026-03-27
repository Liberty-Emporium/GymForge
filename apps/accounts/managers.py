from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    """
    Custom manager for the GymForge User model.

    Ensures the role field is handled correctly when creating users via
    management commands (createsuperuser) and programmatically.
    """

    def _create_user(self, username, email, password, **extra_fields):
        if not username:
            raise ValueError('The username must be set.')
        email = self.normalize_email(email)
        username = self.model.normalize_username(username)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        extra_fields.setdefault('role', 'member')
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'platform_admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(username, email, password, **extra_fields)

    # ------------------------------------------------------------------
    # Convenience querysets
    # ------------------------------------------------------------------

    def members(self):
        return self.filter(role='member')

    def staff_users(self):
        """All non-member, non-platform-admin users (gym staff)."""
        return self.exclude(role__in=['member', 'platform_admin'])

    def by_role(self, role):
        return self.filter(role=role)

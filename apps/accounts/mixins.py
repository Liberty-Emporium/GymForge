from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class RoleRequiredMixin(LoginRequiredMixin):
    """
    Base mixin that enforces a single required role on a class-based view.

    Usage
    -----
    class MyView(OwnerRequiredMixin, View):
        ...

    The user must be authenticated AND have the correct role.
    Unauthenticated users are redirected to LOGIN_URL.
    Authenticated users with the wrong role receive a 403.
    """

    required_role = None  # override in subclass or set on the view directly

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if self.required_role and request.user.role != self.required_role:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class MultiRoleRequiredMixin(LoginRequiredMixin):
    """
    Allows a view to be accessed by any of several roles.

    Usage
    -----
    class MyView(MultiRoleRequiredMixin, View):
        allowed_roles = ['manager', 'gym_owner']
    """

    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if self.allowed_roles and request.user.role not in self.allowed_roles:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# Single-role convenience mixins — one per portal
# ---------------------------------------------------------------------------

class PlatformAdminRequiredMixin(RoleRequiredMixin):
    required_role = 'platform_admin'


class OwnerRequiredMixin(RoleRequiredMixin):
    required_role = 'gym_owner'


class ManagerRequiredMixin(RoleRequiredMixin):
    required_role = 'manager'


class TrainerRequiredMixin(RoleRequiredMixin):
    required_role = 'trainer'


class FrontDeskRequiredMixin(RoleRequiredMixin):
    required_role = 'front_desk'


class CleanerRequiredMixin(RoleRequiredMixin):
    required_role = 'cleaner'


class NutritionistRequiredMixin(RoleRequiredMixin):
    required_role = 'nutritionist'


class MemberRequiredMixin(RoleRequiredMixin):
    required_role = 'member'


# ---------------------------------------------------------------------------
# Combined convenience mixins
# ---------------------------------------------------------------------------

class OwnerOrManagerRequiredMixin(MultiRoleRequiredMixin):
    """Accessible by gym_owner and manager roles."""
    allowed_roles = ['gym_owner', 'manager']


class AnyStaffRequiredMixin(MultiRoleRequiredMixin):
    """Accessible by any staff role (excludes members and platform_admin)."""
    allowed_roles = ['gym_owner', 'manager', 'trainer', 'front_desk', 'cleaner', 'nutritionist']

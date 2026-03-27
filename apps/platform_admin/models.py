from django.db import models


# ---------------------------------------------------------------------------
# Plan — PUBLIC SCHEMA
# GymForge SaaS plans: what gym owners pay the platform owner.
# Lives in apps.platform_admin (SHARED_APPS) so GymTenant.plan FK resolves
# in the public schema.
# ---------------------------------------------------------------------------

class Plan(models.Model):
    """
    GymForge SaaS subscription tiers — Starter / Growth / Pro.

    Starter  — up to 150 members, 1 location,  $79/mo
    Growth   — up to 500 members, 3 locations, $199/mo
    Pro      — unlimited members + locations,  $399/mo
    """

    name = models.CharField(max_length=100)
    max_members = models.IntegerField()
    max_locations = models.IntegerField()
    price_monthly = models.DecimalField(max_digits=8, decimal_places=2)
    stripe_price_id = models.CharField(max_length=100)
    features = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'GymForge Plan'
        verbose_name_plural = 'GymForge Plans'
        ordering = ['price_monthly']

    def __str__(self):
        return f'{self.name} (${self.price_monthly}/mo)'


class AuditLog(models.Model):
    """
    Platform-wide immutable audit trail.

    Lives in the PUBLIC schema (apps.platform_admin is in SHARED_APPS).
    Records every sensitive action across ALL tenant schemas so the
    Platform Owner has full visibility regardless of which gym is active.

    IMMUTABLE — no edit or delete views are ever permitted anywhere.
    Rows are written once and never modified.

    Written by
    ----------
    - Platform Owner impersonation events (Step 18) — always before switching
      tenant context; this is a hard business rule, not a best-effort log.
    - Billing events (subscription activate / suspend / cancel)
    - Any other platform-level action that needs a paper trail

    actor_email     : the user who performed the action
    gym_schema      : tenant schema name, blank for public-schema actions
    action          : human-readable description, e.g. "impersonated tenant ironhouse"
    target_model    : e.g. "GymTenant", "MemberMembership"
    target_id       : pk of the affected row (if applicable)
    details         : arbitrary JSON for extra context
    timestamp       : UTC; set automatically; never writable after insert
    ip_address      : source IP from the request (best-effort)
    """

    actor_email = models.EmailField(db_index=True)
    gym_schema = models.CharField(max_length=100, blank=True, db_index=True)
    action = models.CharField(max_length=200)
    target_model = models.CharField(max_length=100, blank=True)
    target_id = models.IntegerField(null=True, blank=True)
    details = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Audit Log Entry'
        verbose_name_plural = 'Audit Log'

    def __str__(self):
        schema = f' [{self.gym_schema}]' if self.gym_schema else ' [public]'
        return f'{self.timestamp:%Y-%m-%d %H:%M} {self.actor_email}{schema}: {self.action}'

    # ------------------------------------------------------------------
    # Convenience factory — use this everywhere instead of .objects.create()
    # ------------------------------------------------------------------

    @classmethod
    def log(cls, actor_email, action, gym_schema='', target_model='',
            target_id=None, details=None, ip_address=None):
        """
        Write one immutable audit log entry.

        Usage
        -----
        AuditLog.log(
            actor_email=request.user.email,
            action='impersonated tenant ironhouse',
            gym_schema='ironhouse',
            target_model='GymTenant',
            target_id=tenant.pk,
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        """
        return cls.objects.create(
            actor_email=actor_email,
            gym_schema=gym_schema,
            action=action,
            target_model=target_model,
            target_id=target_id,
            details=details or {},
            ip_address=ip_address,
        )

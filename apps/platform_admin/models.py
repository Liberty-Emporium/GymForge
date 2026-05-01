from django.db import models


class Plan(models.Model):
    """
    GymForge SaaS subscription plans (Starter / Growth / Pro).
    One row per plan offered to gym owners.
    """
    name             = models.CharField(max_length=100, unique=True)
    price_monthly    = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    max_members      = models.IntegerField(default=0, help_text='0 = unlimited')
    max_locations    = models.IntegerField(default=1)
    stripe_price_id  = models.CharField(max_length=200, blank=True)
    features         = models.JSONField(default=list, blank=True)
    is_active        = models.BooleanField(default=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['price_monthly']
        verbose_name = 'Plan'
        verbose_name_plural = 'Plans'

    def __str__(self):
        return f'{self.name} (${self.price_monthly}/mo)'


class AuditLog(models.Model):
    """
    Immutable audit trail for the gym deployment.
    Written once on every sensitive action. Never modified or deleted.
    """

    actor_email  = models.EmailField(db_index=True)
    gym_schema   = models.CharField(max_length=100, blank=True, db_index=True)
    action       = models.CharField(max_length=200)
    target_model = models.CharField(max_length=100, blank=True)
    target_id    = models.IntegerField(null=True, blank=True)
    details      = models.JSONField(default=dict)
    timestamp    = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address   = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Audit Log Entry'
        verbose_name_plural = 'Audit Log'

    def __str__(self):
        return f'{self.timestamp:%Y-%m-%d %H:%M} {self.actor_email}: {self.action}'

    @classmethod
    def log(cls, actor_email, action, gym_schema='', target_model='',
            target_id=None, details=None, ip_address=None):
        return cls.objects.create(
            actor_email=actor_email,
            gym_schema=gym_schema,
            action=action,
            target_model=target_model,
            target_id=target_id,
            details=details or {},
            ip_address=ip_address,
        )

from django.db import models


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

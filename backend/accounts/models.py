from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Worker role for a Django account. All accounts are created by an
    admin (no self-signup, no SSO - not everyone has a company email) and
    are workers; the public/customer tier is implicit (unauthenticated),
    not a role stored here.

    Default is SALESPERSON (least privilege) so an admin who creates a user
    and forgets to set the role doesn't accidentally grant management
    access to management-only tools like the commission override.
    """

    ROLE_SALESPERSON = 'SALESPERSON'
    ROLE_ACCOUNTING = 'ACCOUNTING'
    ROLE_MANAGEMENT = 'MANAGEMENT'
    ROLE_CHOICES = [
        (ROLE_SALESPERSON, 'Vendedor'),
        (ROLE_ACCOUNTING, 'Contabilidad'),
        (ROLE_MANAGEMENT, 'Gerencia'),
    ]

    # Same zone codes as commissions.InvoiceCommissionOverride.ZONE_CHOICES.
    # Not consumed anywhere yet - laid down now (2026-09-24) as the
    # foundation for the deferred "salespeople see only their own
    # commissions" feature, so linking an account to a zone doesn't require
    # a schema change later. Deliberately unrestricted (any role can have
    # any zone, including none) since the real per-zone-salesperson
    # constraints aren't settled yet - narrowing this down is easy later,
    # guessing wrong now and having to migrate away from it isn't.
    ZONE_CHOICES = [
        ('ZONA1', 'Zona 1'), ('ZONA2', 'Zona 2'), ('OFICINA', 'Oficina'),
        ('SERVICIOS', 'Servicios'), ('PUNTOVENTA', 'Punto de Venta'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_SALESPERSON)
    zone = models.CharField(max_length=10, choices=ZONE_CHOICES, blank=True)

    def __str__(self):
        return f'{self.user.username} ({self.get_role_display()})'


class AccountAuditLogEntry(models.Model):
    """Who did what to which account, for the self-service /usuarios panel
    (requested 2026-09-24 so account management doesn't depend on one
    developer using the Django admin). Stores usernames as plain text
    snapshots, not live FKs - an audit entry must stay readable even if the
    actor or target account is later renamed or removed, same reasoning as
    why commissions.InvoiceCommissionOverride never stores a live client
    name (see feedback_no_client_pii_in_repo) - a log that changes meaning
    after the fact isn't an audit log.
    """

    ACTION_CREATED = 'CREATED'
    ACTION_ROLE_CHANGED = 'ROLE_CHANGED'
    ACTION_ZONE_CHANGED = 'ZONE_CHANGED'
    ACTION_ACTIVATED = 'ACTIVATED'
    ACTION_DEACTIVATED = 'DEACTIVATED'
    ACTION_PASSWORD_RESET = 'PASSWORD_RESET'
    ACTION_CHOICES = [
        (ACTION_CREATED, 'Cuenta creada'),
        (ACTION_ROLE_CHANGED, 'Rol cambiado'),
        (ACTION_ZONE_CHANGED, 'Zona cambiada'),
        (ACTION_ACTIVATED, 'Cuenta activada'),
        (ACTION_DEACTIVATED, 'Cuenta desactivada'),
        (ACTION_PASSWORD_RESET, 'Contraseña restablecida'),
    ]

    actor_username = models.CharField(max_length=150)
    target_username = models.CharField(max_length=150)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    detail = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.actor_username} -> {self.get_action_display()} ({self.target_username})'

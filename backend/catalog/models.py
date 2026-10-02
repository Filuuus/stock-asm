import secrets

from django.conf import settings
from django.db import models


class ProductImage(models.Model):
    # Not a real ForeignKey: producto_codigo mirrors AdmProductos.CCODIGOPRODUCTO
    # in the ERP (a separate, read-only database) rather than referencing it.
    producto_codigo = models.CharField(max_length=30, db_index=True)
    file = models.CharField(max_length=255)
    order = models.PositiveSmallIntegerField(default=0)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["producto_codigo", "order"]


class ProductPriceVisibility(models.Model):
    """Per-product override of the default "prices are private to workers"
    rule. A product's absence here (or public=False) means its price stays
    worker-only; public=True makes it visible to anyone, logged in or not.
    Starts empty - nothing is public by default (owner's decision, 2026-09).
    """

    # Not a real ForeignKey: mirrors AdmProductos.CCODIGOPRODUCTO in the ERP,
    # same pattern as ProductImage above.
    producto_codigo = models.CharField(max_length=30, unique=True)
    public = models.BooleanField(default=False)

    class Meta:
        ordering = ["producto_codigo"]

    def __str__(self):
        return f'{self.producto_codigo} ({"pública" if self.public else "privada"})'


def _new_token():
    return secrets.token_urlsafe(16)


class QuoteRequest(models.Model):
    """A customer's cart sent for pricing (management, 2026-10-01): prices stay
    private, staff review the request and management approves it, which
    freezes the prices; the customer follows it through their own link
    (/solicitud/<token>). Customer details live only in this local database,
    never in the repo or the ERP.
    """

    STATUS_NEW, STATUS_APPROVED, STATUS_REJECTED = 'NEW', 'APPROVED', 'REJECTED'
    STATUS_CHOICES = [(STATUS_NEW, 'Nueva'), (STATUS_APPROVED, 'Aprobada'), (STATUS_REJECTED, 'Rechazada')]

    token = models.CharField(max_length=32, unique=True, default=_new_token, editable=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_NEW)
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30)
    company = models.CharField(max_length=120, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    valid_until = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Solicitud {self.pk} ({self.get_status_display()})'


class QuoteRequestItem(models.Model):
    request = models.ForeignKey(QuoteRequest, related_name='items', on_delete=models.CASCADE)
    # Mirrors AdmProductos.CCODIGOPRODUCTO, same pattern as ProductImage.
    producto_codigo = models.CharField(max_length=30)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    # Frozen when management approves; null = no price ("se cotiza aparte").
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ['id']
        unique_together = [('request', 'producto_codigo')]

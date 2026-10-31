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


class ProductDescription(models.Model):
    """The product page's description, written by staff (or pre-filled from
    the manufacturer's site). Shown to the public, with any part number in it
    cut out like everywhere else."""

    # Not a real ForeignKey: mirrors AdmProductos.CCODIGOPRODUCTO in the ERP.
    producto_codigo = models.CharField(max_length=30, unique=True)
    text = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)


class SpecialOrderProduct(models.Model):
    """Something we can order but the ERP doesn't have (office samples of Animat's other lines):
    in the catalog as "Sobre pedido", quoted by staff. Its catalog id is SPECIAL_ORDER_ID_OFFSET + pk."""

    code = models.CharField(max_length=30, unique=True)  # what photos, descriptions and quotes point to
    name = models.CharField(max_length=120)


class HiddenProduct(models.Model):
    """Not shown to the public; staff still see it. By catalog id, ERP or special order."""

    product_id = models.PositiveIntegerField(unique=True)


class CategoryRule(models.Model):
    """What the public sees of a catalog category (management decides, /ajustes-catalogo)."""

    ON_ORDER_NEVER, ON_ORDER_ALWAYS, ON_ORDER_IF_SOLD = 'NEVER', 'ALWAYS', 'IF_SOLD'
    ON_ORDER_CHOICES = [(ON_ORDER_NEVER, 'Nunca'), (ON_ORDER_ALWAYS, 'Siempre'),
                        (ON_ORDER_IF_SOLD, 'Si se vendió en 12 meses')]

    category = models.CharField(max_length=10, unique=True)
    show_price = models.BooleanField(default=False)
    on_order = models.CharField(max_length=10, choices=ON_ORDER_CHOICES, default=ON_ORDER_NEVER)
    hide_brand = models.BooleanField(default=False)


class BrandRule(models.Model):
    """The name the public sees for an ERP brand; a brand with no rule isn't shown (it may be a distributor)."""

    erp_name = models.CharField(max_length=120, unique=True)
    public_name = models.CharField(max_length=60)


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
    # Typed by staff, or frozen from the catalog when management approves; null = no price ("se cotiza aparte").
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ['id']
        unique_together = [('request', 'producto_codigo')]

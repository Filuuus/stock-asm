from decimal import Decimal

from django.db import models


class CommissionCategoryRate(models.Model):
    """Base commission % per item category, editable without a code change.

    'S' (Servicios) has two rows because the rate depends on who performed the
    service, not the item alone: S_SALESPERSON when a route salesperson
    (ZONA1/ZONA2) does it as a side task, S_SERVICIOS when the dedicated
    maintenance crew does it. R/B/EQ are one rate each.
    """

    code = models.CharField(max_length=20, unique=True)
    label = models.CharField(max_length=60)
    base_rate = models.DecimalField(max_digits=5, decimal_places=4)
    decay_rate_per_week = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('0.0050'))
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code} ({self.base_rate:.2%})'


class ZeroCommissionProduct(models.Model):
    # Not a real ForeignKey: producto_codigo mirrors AdmProductos.CCODIGOPRODUCTO
    # in the ERP (a separate, read-only database) rather than referencing it.
    producto_codigo = models.CharField(max_length=30, unique=True)
    note = models.CharField(max_length=200, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['producto_codigo']

    def __str__(self):
        return self.producto_codigo

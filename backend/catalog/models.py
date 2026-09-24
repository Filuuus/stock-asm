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

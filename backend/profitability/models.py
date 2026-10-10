from django.conf import settings
from django.db import models


class ProductWeight(models.Model):
    """Kg per sale unit typed in by management for a product whose weight the app could only
    estimate. Wins over every automatic source (see weights.estimate_kg)."""
    # Not a real ForeignKey: mirrors AdmProductos.CIDPRODUCTO in the read-only ERP.
    producto_id = models.IntegerField(unique=True)
    kg = models.DecimalField(max_digits=9, decimal_places=3)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)

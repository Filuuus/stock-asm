from django.db import models


class VehicleDayKm(models.Model):
    """Km each GPS unit drove on one day, read straight from Zeek (Zeek keeps no history from
    before 2026-10-02, so this table is the only long-term record). A row with 0 km means the
    unit was read and didn't move; a missing row means it was never read."""
    imei = models.CharField(max_length=32)
    day = models.DateField()
    km = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['imei', 'day'], name='unique_vehicle_day_km')]

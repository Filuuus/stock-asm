from django.db import models


class VehicleDayKm(models.Model):
    """Km each GPS unit drove on one day, read straight from Zeek (Zeek keeps only about the last
    six days, so this table is the only long-term record). A row with 0 km means the
    unit was read and didn't move; a missing row means it was never read."""
    imei = models.CharField(max_length=32)
    day = models.DateField()
    km = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['imei', 'day'], name='unique_vehicle_day_km')]


class VehicleStop(models.Model):
    """Where a GPS unit stopped: the end of each Zeek trip, until the next trip starts (leave is empty
    for the day's last stop). Kept for matching stops to clients; Zeek drops trips after about six days."""
    imei = models.CharField(max_length=32)
    day = models.DateField()
    arrive = models.DateTimeField()
    leave = models.DateTimeField(null=True, blank=True)
    lat = models.FloatField()
    lng = models.FloatField()
    source = models.CharField(max_length=10)  # 'zeek', or 'notion' for days rescued from the fleet log pages
    # No unique key: a unit's stops are replaced a whole day at a time (save_stops).

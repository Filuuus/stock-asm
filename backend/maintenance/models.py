"""Clients' milking parlors, the wear parts each one has, and what the service plan needs to remember:
part changes staff confirm, visits proposed to the service calendar, and the GEA orders placed.
Clients are bare ERP codes (admClientes.CCODIGOCLIENTE); names are resolved live (the repo is public)."""

from django.db import models


class Parlor(models.Model):
    client_code = models.CharField(max_length=30)
    label = models.CharField(max_length=80, blank=True)  # tells apart two parlors of one client
    stalls = models.PositiveIntegerField()
    cows = models.PositiveIntegerField(null=True, blank=True)
    milking_hours_per_day = models.FloatField(null=True, blank=True)  # converts GEA's hours into months
    active = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.client_code} {self.label}'.strip()


class ParlorPart(models.Model):
    parlor = models.ForeignKey(Parlor, on_delete=models.CASCADE, related_name='parts')
    code = models.CharField(max_length=30)  # ERP product code without GEA's letter suffix
    quantity = models.PositiveIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['parlor', 'code'], name='unique_parlor_part')]


class PartChange(models.Model):
    """A change staff confirmed (or corrected); invoices supply the rest, read live from the ERP."""
    parlor = models.ForeignKey(Parlor, on_delete=models.CASCADE, related_name='changes')
    code = models.CharField(max_length=30)
    date = models.DateField()
    visit = models.ForeignKey('Visit', null=True, blank=True, on_delete=models.SET_NULL, related_name='changes')


class Visit(models.Model):
    """One service visit to a parlor: the parts due in its month. Proposed by the monthly plan,
    moved to a workable date by staff, confirmed once done."""
    STATUS_CHOICES = [('proposed', 'Propuesta'), ('scheduled', 'Agendada'), ('done', 'Realizada'),
                      ('cancelled', 'Cancelada')]
    parlor = models.ForeignKey(Parlor, on_delete=models.CASCADE, related_name='visits')
    month = models.DateField()  # first day of the month the parts fall due
    date = models.DateField(null=True, blank=True)  # the agreed day
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='proposed')
    parts = models.JSONField(default=list)  # [{"code": "...", "quantity": 32}] at proposal time
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['parlor', 'month'], name='unique_parlor_visit_month')]


class OrderLine(models.Model):
    """A part ordered from GEA (the ERP has no purchase orders, only the purchase once it arrives)."""
    month = models.DateField()  # first day of the month it was ordered
    code = models.CharField(max_length=30)
    quantity = models.PositiveIntegerField()
    received_on = models.DateField(null=True, blank=True)

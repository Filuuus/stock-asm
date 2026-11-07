"""Clients' milking parlors and the wear parts each one has (part changes come from the invoices). Clients are bare ERP codes (admClientes.CCODIGOCLIENTE); names are resolved live (the repo is
public)."""

from django.conf import settings
from django.db import models


class Parlor(models.Model):
    client_code = models.CharField(max_length=30)
    label = models.CharField(max_length=80, blank=True)  # tells apart two parlors of one client
    stalls = models.PositiveIntegerField()
    cows = models.PositiveIntegerField(null=True, blank=True)
    milking_hours_per_day = models.FloatField(null=True, blank=True)  # converts GEA's hours into months
    active = models.BooleanField(default=True)
    # Codes staff removed ("No aplica"), so sync_parlors doesn't add them back from the invoices.
    dismissed = models.JSONField(default=list, blank=True)
    # A prospect someone reached out to (a call, a visit), so two people don't call the same farm.
    contacted_at = models.DateTimeField(null=True, blank=True)
    contacted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='+')

    def __str__(self):
        return f'{self.client_code} {self.label}'.strip()


class ParlorPart(models.Model):
    parlor = models.ForeignKey(Parlor, on_delete=models.CASCADE, related_name='parts')
    code = models.CharField(max_length=30)  # ERP product code without GEA's letter suffix
    quantity = models.PositiveIntegerField()
    group = models.CharField(max_length=60, blank=True)  # where it goes, as the calendar groups it (Colectores...)
    sheet_months = models.PositiveIntegerField(null=True, blank=True)  # the calendar's RECAMBIO, last resort

    class Meta:
        # A part can be in two places of a parlor (the same hose on the claws and on the LECC): a row per place.
        constraints = [models.UniqueConstraint(fields=['parlor', 'code', 'group'], name='unique_parlor_part_place')]



class ServiceQuote(models.Model):
    """A quote request made from a parlor's detail (catalog.QuoteRequest) and the parts it covers, so the agenda
    shows them as quoted until they're invoiced."""

    parlor = models.ForeignKey(Parlor, on_delete=models.CASCADE, related_name='quotes')
    request = models.OneToOneField('catalog.QuoteRequest', on_delete=models.CASCADE, related_name='service_quote')
    places = models.JSONField(default=list)  # [[code, group], ...]
    created_at = models.DateTimeField(auto_now_add=True)


class ExternalChange(models.Model):
    """A part changed by someone else (another dealer, the client's own crew): no invoice of ours records it, but
    it restarts the part's interval, so the client can be contacted before the next change."""

    part = models.ForeignKey(ParlorPart, on_delete=models.CASCADE, related_name='external_changes')
    day = models.DateField()
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


class ClientPhone(models.Model):
    """A client's phone as staff typed it, over Contpaqi's (often missing or a landline), for WhatsApp. Lives only
    in this local database: the ERP is read-only and the repo public."""

    client_code = models.CharField(max_length=30, unique=True)
    phone = models.CharField(max_length=30)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

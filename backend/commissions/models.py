from decimal import Decimal

from django.conf import settings
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


class PuntoVentaClientZone(models.Model):
    """Which route salesperson (ZONA1/ZONA2) a Punto de Venta subdistributor
    client actually belongs to - confirmed by management 2026-09-19: invoices
    tagged CIDAGENTE=PUNTOVENTA are subdistributor clients, not office
    walk-ins, and their commission is supposed to go to whichever salesman
    is responsible for that client, at a flat rate (see the PUNTOVENTA
    CommissionCategoryRate) rather than the usual per-category rate.

    Nothing in the ERP records this assignment (checked admClientes.
    CIDAGENTEVENTA/CIDAGENTECOBRO - both are just "PUNTOVENTA" for 99.8% of
    these clients too), so this is app-owned config, same pattern as
    ZeroCommissionProduct.

    Deliberately does NOT store the client's name (2026-09-19): this table
    is small enough to seed directly in a migration, and this repo is
    public - a bare cliente_id is meaningless without ERP access, but a
    real person/business name next to it would be actual client PII sitting
    in source control. The admin looks the name up live from the ERP
    (AdmClientes) for display instead of caching it here.
    """
    ZONE_CHOICES = [('ZONA1', 'Zona 1'), ('ZONA2', 'Zona 2')]

    # Not a real ForeignKey: mirrors AdmClientes.CIDCLIENTEPROVEEDOR in the
    # ERP (a separate, read-only database) rather than referencing it.
    cliente_id = models.IntegerField(unique=True)
    zone = models.CharField(max_length=10, choices=ZONE_CHOICES)
    note = models.CharField(max_length=200, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['cliente_id']

    def __str__(self):
        return f'Cliente {self.cliente_id} -> {self.zone}'


class InvoiceCommissionOverride(models.Model):
    """Management-only manual correction to one invoice's commission -
    the "Add"/"Exclude" tool on the Comisiones dashboard. Requested
    2026-09-19 (see sales-commissions-feature memory) for cases the
    automatic per-line calculation gets wrong that aren't worth a general
    rule (e.g. a genuine one-off management judgment call, or a rare
    category like Equipo with no automatic detection rule yet).

    Two independent modes, both keyed by invoice_id:
    - excluded=True: the invoice's computed commission is zeroed out and
      excluded from zone_totals, but its row stays visible (grayed/struck
      through), not deleted from the response - management wants to see
      *what* was excluded, not just a smaller number.
    - override_amount set: replaces the invoice's commission with this flat
      amount (not additive) - covers "the automatic calculation used the
      wrong rate/category" rather than "this shouldn't count at all".

    zone is only needed when the invoice isn't naturally present in the
    computed set at all (found via the invoice-search endpoint - outside
    the normal lookback window, a different classification, etc.) - when it
    resolves naturally its real zone from the ERP is used instead.

    Same PII rule as PuntoVentaClientZone: never store the client name here,
    only the ERP invoice id - resolved live from AdmDocumentos for display.
    """

    ZONE_CHOICES = [
        ('ZONA1', 'Zona 1'), ('ZONA2', 'Zona 2'), ('OFICINA', 'Oficina'),
        ('SERVICIOS', 'Servicios'), ('PUNTOVENTA', 'Punto de Venta'),
    ]

    # Not a real ForeignKey: mirrors AdmDocumentos.CIDDOCUMENTO in the ERP
    # (a separate, read-only database) rather than referencing it.
    invoice_id = models.IntegerField(unique=True)
    excluded = models.BooleanField(default=False)
    override_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    zone = models.CharField(max_length=10, choices=ZONE_CHOICES, blank=True)
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        if self.excluded:
            return f'Factura {self.invoice_id}: excluida'
        return f'Factura {self.invoice_id}: monto manual {self.override_amount}'

from django.conf import settings
from django.db import models


class CorteDeCajaAdjustment(models.Model):
    """Accounting/management annotation on one payment-collection EVENT for
    the Corte de Caja dashboard - rebuilt 2026-09-24 after comparing the
    first version against the real "Corte de caja 2026.xlsx" sheet, which
    turned out to be a daily CASH-COLLECTIONS reconciliation (money received
    per invoice per day), not an accounts-receivable/aging view. See
    corte_de_caja/services.py for the full story and the corte-de-caja-
    dashboard project memory.

    Keyed by (invoice_id, event_date) rather than invoice_id alone, because
    one invoice can be paid off across several installments on different
    days (an "abono" in the original sheet's DEBE column) - each is its own
    collection event needing its own tag, not one adjustment per invoice.

    Two things an entry can hold, both writable by either ACCOUNTING or
    MANAGEMENT (this is their shared daily workflow, like the rest of this
    app - not management-only like commissions' override):
    - payment_method: how the money physically came in (efectivo/terminal/
      cheque/transferencia). NOT derivable from the ERP - checked live
      against real payment documents and the field that might have hinted
      at it (CCONDIPAGO) is blank on every row, and the document type that
      exists for this ("Cheque recibido") isn't actually used in practice.
      This has to be a human call, same category of gap as commissions'
      EQ-equipment detection (no signal exists, accepted as a manual input
      rather than guessed at). Once tagged, the EFECTIVO/TERMINAL/CHEQUE/
      TOTAL CORTE cash-drawer totals compute themselves from these tags
      instead of being hand-typed arithmetic like the original sheet.
    - excluded / reviewed / note: same purpose as the rest of this app's
      correction tools - pull a bad match out of the totals, mark it
      checked, leave an observación.

    Same PII rule as the commissions overrides: never store the client's
    name, only the ERP invoice id.
    """

    PAYMENT_METHOD_EFECTIVO = 'EFECTIVO'
    PAYMENT_METHOD_TERMINAL = 'TERMINAL'
    PAYMENT_METHOD_CHEQUE = 'CHEQUE'
    PAYMENT_METHOD_TRANSFERENCIA = 'TRANSFERENCIA'
    PAYMENT_METHOD_CHOICES = [
        (PAYMENT_METHOD_EFECTIVO, 'Efectivo'),
        (PAYMENT_METHOD_TERMINAL, 'Terminal'),
        (PAYMENT_METHOD_CHEQUE, 'Cheque'),
        (PAYMENT_METHOD_TRANSFERENCIA, 'Transferencia'),
    ]

    # Not a real ForeignKey: mirrors AdmDocumentos.CIDDOCUMENTO in the ERP
    # (a separate, read-only database) rather than referencing it.
    invoice_id = models.IntegerField()
    event_date = models.DateField()

    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, blank=True)
    reviewed = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='corte_de_caja_reviews',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    excluded = models.BooleanField(default=False)
    note = models.CharField(max_length=200, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='corte_de_caja_adjustments',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(fields=['invoice_id', 'event_date'], name='unique_corte_de_caja_event'),
        ]

    def __str__(self):
        return f'Factura {self.invoice_id} ({self.event_date}): ajuste Corte de Caja'

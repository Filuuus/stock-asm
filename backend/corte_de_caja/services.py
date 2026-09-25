"""Daily cash-collections reconciliation - the automatic replacement for the
manually-built "Corte de Caja Cobranza General" Excel sheet.

CORRECTION (2026-09-24): an earlier version of this module built an
accounts-receivable/aging report (owed/paid/due-date per invoice). After the
user restored the real "Corte de caja 2026.xlsx" workbook and pointed out it
didn't match at all, inspecting it directly (185 daily sheets, one business
day each) showed the real report is something else entirely: a log of MONEY
COLLECTED that day, one row per payment applied to an invoice - including
partial payments ("abonos", not just full settlements) - grouped by zone,
with a bottom-of-sheet cash-drawer reconciliation (TOTAL EFECTIVO/TERMINAL/
CHEQUES/CORTE). See the corte-de-caja-dashboard project memory for the full
column-by-column findings.

Two real columns from the original sheet are NOT reproduced here, checked
live against the ERP and confirmed not derivable:
- WHO physically collected the cash (the sheet's per-salesperson block
  grouping) - every real payment document's CUSUARIO is the same generic
  'SUPERVISOR' login, no signal at all. Dropped per the user's direction;
  zone (COMISION) totals are kept instead.
- Payment method (efectivo/terminal/cheque/transferencia) as a single,
  reliable field - checked a real cheque-tagged row against its actual ERP
  document: same generic "Pago del cliente" type as every other payment,
  CCONDIPAGO blank on every row, admFormasPago never configured (only the
  default placeholder row), the CFDI payment-complement tables unused.

CORRECTION #2 (2026-09-24, same day): the Contabilidad ledger DOES carry a
real, useful signal here after all - each "PAGO DEL CLIENTE" Poliza has a
line crediting the client (which the pipeline above already reads) AND a
separate line debiting the real bank account the money landed in, which the
first cut of this module was filtering out (it only kept Referencia-
populated lines). Checked live: every actual payment in 2026 debits one of
a handful of real bank accounts - the business's Caja Chica (cash) account
is used exactly once all year. So this identifies WHICH BANK, not cash vs.
terminal vs. cheque vs. transfer directly - per the user, since bank wires
are the dominant real case, a known bank now AUTO-SUGGESTS "Transferencia"
(or "Efectivo" for the rare Caja Chica case) rather than leaving every row
blank. This is a suggestion, not a verified fact - `payment_method_confirmed`
stays False until a human accepts or corrects it, and it still counts
toward the totals (per the user: populate as many fields as possible,
minimize manual input, an occasional wrong guess is an acceptable trade for
not making the accountant tag hundreds of rows by hand).

Reuses commissions.services directly for everything that IS derivable and
already verified there: the real-sale/zone-scope filter, the Contabilidad-
ledger payment resolution (the itemized per-invoice payment ledger, primary
source), and the Comercial-side CREFERENCIA fallback - see that module for
the full history of getting this right. The one new piece here is emitting
EVERY dated payment installment in the window (an event log), not just the
single date an invoice finally reached zero balance the way commissions
needs - a partial abono is a real cash-collection event for this report even
though it isn't a commission-earning one for that report.
"""

from collections import defaultdict
from datetime import timedelta, timezone as dt_timezone
from decimal import Decimal

from django.utils import timezone as dj_timezone

from commissions.services import (
    LEDGER_FULL_PAYMENT_TOLERANCE,
    CommissionRepository,
    _classify_line,
    _extract_folio_tokens,
    _normalize_name,
)

from .models import CorteDeCajaAdjustment

# How far back to look for candidate Facturas relative to date_from - a
# large equipment sale can take months to settle via installments (see
# commissions' CIDDOCUMENTO 100223, a ~6-month spread), so this is wider
# than commissions' own 120-day DEFAULT_LOOKBACK_DAYS.
CANDIDATE_LOOKBACK_DAYS = 365

# Chart-of-accounts code prefixes under "Circulante" - checked live
# 2026-09-24 (ctAGROPECUARIA_SANTA_MARIA_SA_DE_CV.dbo.Cuentas): '100101' is
# Caja Chica (cash, used once in all of 2026), '100102' is Bancos (the 4
# real bank accounts every actual payment debits in practice).
CASH_ACCOUNT_CODE_PREFIX = '100101'
BANK_ACCOUNT_CODE_PREFIX = '100102'
PAYMENT_METHOD_EFECTIVO = CorteDeCajaAdjustment.PAYMENT_METHOD_EFECTIVO
PAYMENT_METHOD_TRANSFERENCIA = CorteDeCajaAdjustment.PAYMENT_METHOD_TRANSFERENCIA


def _as_decimal(value):
    return Decimal(str(round(value, 2))) if value is not None else Decimal('0')


def _poliza_bank_accounts(ledger_lines, bank_accounts):
    """For each Poliza, the single unambiguous bank/cash account its
    blank-Referencia debit line(s) point to (see fetch_ledger_payment_lines)
    - None if the poliza has no such line, or splits across more than one
    account (checked live: ~0.5% of real 2026 PAGO DEL CLIENTE polizas -
    left unresolved rather than guessing which invoice's money went where).
    """
    accounts_by_poliza = defaultdict(set)
    for id_poliza, referencia, fecha, concepto, importe, tipo_movto, id_cuenta in ledger_lines:
        if referencia or tipo_movto:
            continue  # referenced (client/IVA) line, or a credit - not the bank debit
        codigo, _ = bank_accounts.get(id_cuenta, (None, None))
        if codigo and (codigo.startswith(CASH_ACCOUNT_CODE_PREFIX) or codigo.startswith(BANK_ACCOUNT_CODE_PREFIX)):
            accounts_by_poliza[id_poliza].add(id_cuenta)
    return {
        poliza_id: next(iter(accounts)) for poliza_id, accounts in accounts_by_poliza.items()
        if len(accounts) == 1
    }


def _suggest_payment_method(account_id, bank_accounts):
    codigo, nombre = bank_accounts.get(account_id, (None, None))
    if codigo is None:
        return None, None
    method = PAYMENT_METHOD_EFECTIVO if codigo.startswith(CASH_ACCOUNT_CODE_PREFIX) else PAYMENT_METHOD_TRANSFERENCIA
    return method, nombre


def _resolve_ledger_events(facturas, ledger_lines, concepto_series, bank_accounts, date_from, date_to):
    """Every dated, netted installment event the Contabilidad ledger records
    against a candidate Factura, restricted to [date_from, date_to] - unlike
    commissions.services._resolve_payment_dates_from_ledger (which this
    mirrors), this does NOT collapse to only the date the invoice reached
    full payment; a partial abono is its own event here. `abono` is set by
    walking the SAME cumulative-vs-CTOTAL logic that function uses, just
    keeping every step instead of only the one that clears the balance.

    Also resolves each event's bank (see _poliza_bank_accounts) and derives
    a suggested payment_method from it - only when every ledger line netted
    into that date came from the SAME poliza, so a single event never mixes
    two different Polizas' banks.

    Returns (events, covered_invoice_ids) - covered_invoice_ids lists which
    Facturas got at least one event from the ledger IN THIS WINDOW, so the
    Comercial-side fallback below only fills in what the ledger didn't.
    """
    poliza_bank = _poliza_bank_accounts(ledger_lines, bank_accounts)

    by_reference = defaultdict(list)
    for id_poliza, referencia, fecha, concepto, importe, tipo_movto, id_cuenta in ledger_lines:
        if not referencia:
            continue
        if dj_timezone.is_naive(fecha):
            fecha = dj_timezone.make_aware(fecha, dt_timezone.utc)
        signed_amount = importe if tipo_movto else -importe
        by_reference[referencia.upper()].append((fecha, _normalize_name(concepto), signed_amount, id_poliza))

    events = []
    covered_invoice_ids = set()
    for f in facturas:
        serie = concepto_series.get(f['CIDCONCEPTODOCUMENTO'], 'F')
        folio = int(f['CFOLIO'])
        client_name = _normalize_name(f['CRAZONSOCIAL'])
        total = f['CTOTAL'] or 0

        by_date = defaultdict(float)
        polizas_by_date = defaultdict(set)
        for referencia in (f'{serie}-{folio}'.upper(), f'{serie} {folio}'.upper()):
            for fecha, ledger_client_name, signed_amount, id_poliza in by_reference.get(referencia, []):
                if client_name and client_name not in ledger_client_name:
                    continue
                by_date[fecha.date()] += signed_amount
                polizas_by_date[fecha.date()].add(id_poliza)
        if not by_date:
            continue

        cumulative = 0.0
        for event_date in sorted(by_date):
            amount = by_date[event_date]
            cumulative += amount
            # Netted entries carry the same few-cents rounding noise
            # LEDGER_FULL_PAYMENT_TOLERANCE already accounts for elsewhere
            # (see commissions.services) - found live 2026-09-24: a stray
            # -$0.02 "event" on an otherwise fully-settled invoice, not a
            # real collection.
            if abs(amount) < LEDGER_FULL_PAYMENT_TOLERANCE:
                continue
            if date_from <= event_date <= date_to:
                covered_invoice_ids.add(f['CIDDOCUMENTO'])
                account_id = None
                polizas = polizas_by_date[event_date]
                if len(polizas) == 1:
                    account_id = poliza_bank.get(next(iter(polizas)))
                suggested_method, bank_name = _suggest_payment_method(account_id, bank_accounts)
                events.append({
                    'invoice_id': f['CIDDOCUMENTO'],
                    'factura': f,
                    'event_date': event_date,
                    'amount': _as_decimal(amount),
                    'abono': cumulative < total - LEDGER_FULL_PAYMENT_TOLERANCE,
                    'source': 'ledger',
                    'approximate': False,
                    'suggested_method': suggested_method,
                    'bank': bank_name,
                })
    return events, covered_invoice_ids


def _resolve_fallback_events(facturas, payment_docs, ledger_covered_ids, date_from, date_to):
    """Comercial-side CREFERENCIA events for candidate Facturas the ledger
    didn't cover in this window - same folio+client matching commissions'
    own fallback uses. The Comercial payment document only carries ONE total
    for the whole payment, not a per-invoice split (only the ledger has
    that), so when one payment document's reference matches more than one
    Factura here its amount can't be safely divided - each match is emitted
    with the document's full CTOTAL and flagged `approximate` so the
    dashboard can surface it for a human to check, rather than guessing a
    split.
    """
    by_folio_client = defaultdict(list)
    for f in facturas:
        if f['CIDDOCUMENTO'] in ledger_covered_ids:
            continue
        by_folio_client[(int(f['CFOLIO']), f['CIDCLIENTEPROVEEDOR'])].append(f)

    events = []
    for pago in payment_docs:
        event_date = pago['CFECHA'].date()
        if not (date_from <= event_date <= date_to):
            continue
        cliente = pago['CIDCLIENTEPROVEEDOR']
        matched = []
        for token in _extract_folio_tokens(pago['CREFERENCIA']):
            matched.extend(by_folio_client.get((int(token), cliente), []))
        if not matched:
            continue
        amount = _as_decimal(pago['CTOTAL'])
        for f in matched:
            events.append({
                'invoice_id': f['CIDDOCUMENTO'],
                'factura': f,
                'event_date': event_date,
                'amount': amount,
                'abono': None,
                'source': 'fallback',
                'approximate': len(matched) > 1,
                # No poliza to trace a bank from - this path only exists for
                # invoices the ledger didn't cover in this window at all.
                'suggested_method': None,
                'bank': None,
            })
    return events


def _dominant_categories(invoice_ids):
    """One category badge per invoice, for display only (not a rate
    calculation the way commissions needs per-line precision) - the
    category with the largest total net amount among the invoice's lines,
    reusing commissions' own verified classification rule rather than
    re-deriving it.
    """
    movimientos = CommissionRepository.fetch_movimientos(invoice_ids)
    product_ids = {m['CIDPRODUCTO'] for m in movimientos}
    productos_by_id = {p['CIDPRODUCTO']: p for p in CommissionRepository.fetch_productos(product_ids)}
    brand_names = CommissionRepository.fetch_brand_names()
    zero_codes = set()  # zero-commission classification is a commissions-only concept, irrelevant here

    totals = defaultdict(lambda: defaultdict(float))
    for m in movimientos:
        producto = productos_by_id.get(m['CIDPRODUCTO'])
        if producto is None:
            continue
        category = _classify_line(producto, brand_names, zero_codes)
        discount = sum((m.get(f'CDESCUENTO{i}') or 0) for i in range(1, 6))
        totals[m['CIDDOCUMENTO']][category] += (m['CNETO'] or 0) - discount

    return {
        invoice_id: max(cats.items(), key=lambda kv: kv[1])[0]
        for invoice_id, cats in totals.items()
    }


def calculate_corte_de_caja(date_from, date_to):
    """Cash collected against real Facturas with a payment event dated in
    [date_from, date_to]. Returns per-zone/per-method totals and a
    per-event row list.
    """
    facturas = CommissionRepository.fetch_facturas_for_corte(date_from, date_to, CANDIDATE_LOOKBACK_DAYS)
    floor_date = date_from - timedelta(days=CANDIDATE_LOOKBACK_DAYS)

    concepto_series = CommissionRepository.fetch_concepto_series()
    bank_accounts = CommissionRepository.fetch_bank_accounts()
    ledger_lines = CommissionRepository.fetch_ledger_payment_lines(floor_date)
    ledger_events, ledger_covered_ids = _resolve_ledger_events(
        facturas, ledger_lines, concepto_series, bank_accounts, date_from, date_to,
    )

    payment_docs = CommissionRepository.fetch_payment_docs(floor_date)
    fallback_events = _resolve_fallback_events(facturas, payment_docs, ledger_covered_ids, date_from, date_to)

    all_events = ledger_events + fallback_events

    agent_codes = CommissionRepository.fetch_agent_codes()
    categories = _dominant_categories(list({e['invoice_id'] for e in all_events}))
    adjustments = {
        (a.invoice_id, a.event_date): a for a in CorteDeCajaAdjustment.objects.filter(
            invoice_id__in={e['invoice_id'] for e in all_events}
        )
    }

    zone_totals = defaultdict(Decimal)
    method_totals = defaultdict(Decimal)
    rows = []
    unclassified_total = Decimal('0')
    unconfirmed_total = Decimal('0')
    approximate_count = 0

    for event in all_events:
        factura = event['factura']
        zone_code = agent_codes.get(factura['CIDAGENTE'])
        adjustment = adjustments.get((event['invoice_id'], event['event_date']))
        excluded = bool(adjustment and adjustment.excluded)
        manual_method = adjustment.payment_method if adjustment else ''
        # A human-confirmed tag always wins; otherwise fall back to the
        # bank-derived suggestion (see _resolve_ledger_events) - still
        # unconfirmed, but populated, per the user's direction to minimize
        # how much needs manual attention rather than requiring every row
        # to be tagged by hand.
        payment_method = manual_method or event['suggested_method'] or ''
        confirmed = bool(manual_method)

        if event['approximate']:
            approximate_count += 1

        if not excluded:
            zone_totals[zone_code] += event['amount']
            if payment_method:
                method_totals[payment_method] += event['amount']
                if not confirmed:
                    unconfirmed_total += event['amount']
            else:
                unclassified_total += event['amount']

        rows.append({
            'invoice_id': event['invoice_id'],
            'event_date': event['event_date'],
            'folio': factura['CFOLIO'],
            'cliente': factura['CRAZONSOCIAL'],
            'zone': zone_code,
            'due_date': factura['CFECHAVENCIMIENTO'],
            'category': categories.get(event['invoice_id']),
            'amount': event['amount'],
            'abono': event['abono'],
            'source': event['source'],
            'approximate': event['approximate'],
            'excluded': excluded,
            'bank': event['bank'],
            'payment_method': payment_method,
            'payment_method_confirmed': confirmed,
            'reviewed': bool(adjustment and adjustment.reviewed),
            'reviewed_by': adjustment.reviewed_by.username if adjustment and adjustment.reviewed_by else None,
            'note': adjustment.note if adjustment else '',
        })

    rows.sort(key=lambda r: (r['event_date'], r['zone'] or ''), reverse=False)

    # The physical cash-drawer total (TOTAL CORTE on the original sheet)
    # excludes bank transfers - those never hit the till, they're recorded
    # separately. Unclassified amounts are excluded from every total below
    # until tagged, rather than guessed into a bucket.
    cash_drawer_total = sum(
        (amount for method, amount in method_totals.items()
         if method != CorteDeCajaAdjustment.PAYMENT_METHOD_TRANSFERENCIA),
        Decimal('0'),
    )

    return {
        'date_from': date_from,
        'date_to': date_to,
        'zone_totals': dict(zone_totals),
        'method_totals': dict(method_totals),
        'cash_drawer_total': cash_drawer_total,
        'rows': rows,
        'unclassified': {
            'count': len([r for r in rows if not r['payment_method'] and not r['excluded']]),
            'total_amount': unclassified_total,
            'note': (
                'Pagos sin forma de pago identificable (ni banco rastreado) - clasifique cada uno '
                '(Efectivo/Terminal/Cheque/Transferencia) para que se incluyan en los totales.'
            ),
        },
        'unconfirmed': {
            'count': len([r for r in rows if r['payment_method'] and not r['payment_method_confirmed'] and not r['excluded']]),
            'total_amount': unconfirmed_total,
            'note': (
                'Forma de pago sugerida automáticamente según el banco que recibió el pago, aún sin '
                'confirmar por un usuario - revise y corrija los que no sean transferencias reales.'
            ),
        },
        'approximate': {
            'count': approximate_count,
            'note': (
                'Pago registrado en Contpaqi Comercial que cubre más de una factura - el monto '
                'mostrado es el total del pago completo, no un desglose verificado por factura.'
            ),
        },
    }

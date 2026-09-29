"""Comercial vs Contabilidad payment dates, per payment - the "Diferencias
de fecha" tab of the Corte de Caja dashboard.

Requested by the accountant 2026-09-28: a payment registered in Contpaqi
Comercial at the end of a month whose poliza is dated in the next month
(May 30 -> Jun 1 is the typical case) is declared in a different tax period
depending on which system you read, and that mismatch is behind the
company's SAT problems. The corte itself always uses the Contabilidad date
(see services.py); this view shows where Comercial disagrees.

Both sides are exact records, paired per invoice:
- Contabilidad: the ledger events the corte uses (services._resolve_ledger_events).
- Comercial: admAsocCargosAbonos, which says which payment was applied to
  which invoice for how much (see CommissionRepository.fetch_comercial_applications).
Measured on 2026 (Jan-Sep): 3,756 of 3,801 ledger events pair 1:1 by
invoice and amount, 50 of them in different months ($511k).

Pairing is done over all the history fetched, and only then filtered to the
requested period, so a May 30 -> Jun 1 pair shows up both when viewing May
and when viewing June - never half of it as a one-sided row.
"""

from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from itertools import combinations

from commissions.services import LEDGER_FULL_PAYMENT_TOLERANCE, CommissionRepository

from .services import (
    CANDIDATE_LOOKBACK_DAYS,
    _as_decimal,
    _invoice_series,
    _resolve_ledger_events,
)

STATUS_SAME_DAY = 'mismo_dia'
STATUS_DIFFERENT_DAY = 'distinto_dia'
STATUS_DIFFERENT_MONTH = 'distinto_mes'
STATUS_COMERCIAL_ONLY = 'solo_comercial'
STATUS_CONTABILIDAD_ONLY = 'solo_contabilidad'
STATUSES = (
    STATUS_DIFFERENT_MONTH, STATUS_COMERCIAL_ONLY, STATUS_CONTABILIDAD_ONLY,
    STATUS_DIFFERENT_DAY, STATUS_SAME_DAY,
)

TOLERANCE = Decimal(str(LEDGER_FULL_PAYMENT_TOLERANCE))
# One payment is sometimes recorded as two or three pieces on one side only
# (e.g. A 4286: one Comercial payment, two polizas of 2,623.04 and 29.87).
# Combinations are only tried among an invoice's leftovers, which are few.
MAX_GROUP_SIZE = 3
MAX_LEFTOVERS_FOR_GROUPING = 12


def _sums_to(items, target):
    return abs(sum(i['amount'] for i in items) - target) <= TOLERANCE


def _pair_invoice(ledger, comercial):
    """Pairs one invoice's ledger events with its Comercial applications.
    Returns a list of (ledger_items, comercial_items); one side is empty for
    a payment only one system has."""
    ledger = sorted(ledger, key=lambda i: i['date'])
    comercial = sorted(comercial, key=lambda i: i['date'])
    matches = []

    # Same amount, one to one, nearest date first.
    for c in comercial:
        candidates = [l for l in ledger if not l.get('used') and abs(l['amount'] - c['amount']) <= TOLERANCE]
        if candidates:
            l = min(candidates, key=lambda l: abs((l['date'] - c['date']).days))
            l['used'] = c['used'] = True
            matches.append(([l], [c]))

    # One payment split into pieces on one side only.
    for one_side, other_side, as_pair in (
        (comercial, ledger, lambda one, many: (many, [one])),
        (ledger, comercial, lambda one, many: ([one], many)),
    ):
        leftovers = [i for i in other_side if not i.get('used')]
        if len(leftovers) > MAX_LEFTOVERS_FOR_GROUPING:
            continue
        for item in one_side:
            if item.get('used'):
                continue
            leftovers = [i for i in other_side if not i.get('used')]
            group = next((
                list(combo)
                for size in range(2, MAX_GROUP_SIZE + 1)
                for combo in combinations(leftovers, size)
                if _sums_to(combo, item['amount'])
            ), None)
            if group:
                item['used'] = True
                for g in group:
                    g['used'] = True
                matches.append(as_pair(item, group))

    matches.extend(([l], []) for l in ledger if not l.get('used'))
    matches.extend(([], [c]) for c in comercial if not c.get('used'))
    return matches


def _status(ledger_items, comercial_items):
    if not ledger_items:
        return STATUS_COMERCIAL_ONLY
    if not comercial_items:
        return STATUS_CONTABILIDAD_ONLY
    ledger_dates = {i['date'] for i in ledger_items}
    comercial_dates = {i['date'] for i in comercial_items}
    if {(d.year, d.month) for d in ledger_dates} != {(d.year, d.month) for d in comercial_dates}:
        return STATUS_DIFFERENT_MONTH
    if ledger_dates != comercial_dates:
        return STATUS_DIFFERENT_DAY
    return STATUS_SAME_DAY


def calculate_date_differences(date_from, date_to):
    """Every customer payment on a real (zone-scoped) Factura with a
    Comercial or Contabilidad date in [date_from, date_to], each with both
    dates side by side and a status."""
    floor_date = date_from - timedelta(days=CANDIDATE_LOOKBACK_DAYS)
    today = date.today()
    # Up to today, not date_to: a payment can be dated before its own
    # invoice, and the pairing mustn't depend on the requested period.
    facturas = CommissionRepository.fetch_scoped_facturas(floor_date, today)
    facturas_by_id = {f['CIDDOCUMENTO']: f for f in facturas}

    ledger_events, _ = _resolve_ledger_events(
        facturas,
        CommissionRepository.fetch_ledger_payment_lines(floor_date),
        CommissionRepository.fetch_concepto_series(),
        CommissionRepository.fetch_bank_accounts(),
        floor_date, today,
    )
    ledger_by_invoice = {}
    for e in ledger_events:
        ledger_by_invoice.setdefault(e['invoice_id'], []).append(
            {'date': e['event_date'], 'amount': e['amount'], 'polizas': e['polizas']}
        )

    comercial_by_invoice = {}
    for invoice_id, _, payment_date, applied_date, amount, serie, folio in (
        CommissionRepository.fetch_comercial_applications(floor_date)
    ):
        if invoice_id not in facturas_by_id or abs(amount or 0) < LEDGER_FULL_PAYMENT_TOLERANCE:
            continue
        comercial_by_invoice.setdefault(invoice_id, []).append({
            'date': payment_date.date(),
            'applied_date': applied_date.date(),
            'amount': _as_decimal(amount),
            'documento': ' '.join(filter(None, [serie, str(int(folio))])),
        })

    in_period = []
    for invoice_id in ledger_by_invoice.keys() | comercial_by_invoice.keys():
        for ledger_items, comercial_items in _pair_invoice(
            ledger_by_invoice.get(invoice_id, []), comercial_by_invoice.get(invoice_id, []),
        ):
            dates = [i['date'] for i in ledger_items + comercial_items]
            if any(date_from <= d <= date_to for d in dates):
                in_period.append((invoice_id, ledger_items, comercial_items))

    agent_codes = CommissionRepository.fetch_agent_codes()
    invoice_series = _invoice_series({invoice_id for invoice_id, _, _ in in_period})
    poliza_labels = CommissionRepository.fetch_poliza_labels(
        {p for _, ledger_items, _ in in_period for i in ledger_items for p in i['polizas']}
    )

    rows = []
    for invoice_id, ledger_items, comercial_items in in_period:
        factura = facturas_by_id[invoice_id]
        status = _status(ledger_items, comercial_items)
        contabilidad_date = max((i['date'] for i in ledger_items), default=None)
        comercial_date = max((i['date'] for i in comercial_items), default=None)
        rows.append({
            'invoice_id': invoice_id,
            'folio_display': f"{invoice_series.get(invoice_id, 'F')} {int(factura['CFOLIO'])}",
            'client_id': factura['CIDCLIENTEPROVEEDOR'],
            'cliente': factura['CRAZONSOCIAL'],
            'zone': agent_codes.get(factura['CIDAGENTE']),
            'invoice_date': factura['CFECHA'].date(),
            'amount': sum((i['amount'] for i in (ledger_items or comercial_items)), Decimal('0')),
            'status': status,
            'comercial_date': comercial_date,
            'contabilidad_date': contabilidad_date,
            'days_difference': (
                (contabilidad_date - comercial_date).days if contabilidad_date and comercial_date else None
            ),
            'comercial': [
                {'date': i['date'], 'applied_date': i['applied_date'], 'amount': i['amount'], 'documento': i['documento']}
                for i in sorted(comercial_items, key=lambda i: i['date'])
            ],
            'contabilidad': [
                {'date': i['date'], 'amount': i['amount'],
                 'polizas': [poliza_labels.get(p, str(p)) for p in i['polizas']]}
                for i in sorted(ledger_items, key=lambda i: i['date'])
            ],
        })
    rows.sort(key=lambda r: (STATUSES.index(r['status']), min(filter(None, [r['comercial_date'], r['contabilidad_date']])),
                             r['folio_display']))

    counts = Counter(r['status'] for r in rows)
    amounts = Counter()
    for r in rows:
        amounts[r['status']] += r['amount']
    return {
        'date_from': date_from,
        'date_to': date_to,
        'rows': rows,
        'totals': {
            status: {'count': counts.get(status, 0), 'total_amount': amounts.get(status, Decimal('0'))}
            for status in STATUSES
        },
    }

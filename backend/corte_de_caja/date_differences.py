"""Comercial vs Contabilidad, per payment - the "Discrepancias" tab of the
Corte de Caja dashboard (called "Diferencias de fecha" until 2026-09-29,
when it also started flagging different amounts and mistyped folios).

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
# A one-sided Comercial payment and a one-sided poliza this close in date and
# amount are most likely the same payment typed with a different amount
# (B 19236: $1,753 in Comercial, $1,756 in the poliza, same day).
STATUS_DIFFERENT_AMOUNT = 'monto_distinto'
DIFFERENT_AMOUNT_MAX_DAYS = 3
DIFFERENT_AMOUNT_MAX_RATIO = Decimal('0.05')
# The same payment on two invoices whose folios differ by one digit or two
# swapped digits: the poliza cites a mistyped folio (Ingresos 264 cites
# F 20317, another client's invoice; Comercial applied the payment to F 20377).
STATUS_WRONG_FOLIO = 'folio_equivocado'
STATUSES = (
    STATUS_DIFFERENT_MONTH, STATUS_WRONG_FOLIO, STATUS_DIFFERENT_AMOUNT,
    STATUS_COMERCIAL_ONLY, STATUS_CONTABILIDAD_ONLY,
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


def pair_payments(ledger, comercial):
    """_pair_invoice plus the "monto distinto" pass over what it leaves
    one-sided. Returns a list of (ledger_items, comercial_items, status)."""
    matches = []
    only_ledger, only_comercial = [], []
    for ledger_items, comercial_items in _pair_invoice(ledger, comercial):
        if not comercial_items:
            only_ledger.append(ledger_items[0])
        elif not ledger_items:
            only_comercial.append(comercial_items[0])
        else:
            matches.append((ledger_items, comercial_items, _status(ledger_items, comercial_items)))
    for c in only_comercial:
        close = [
            l for l in only_ledger
            if abs((l['date'] - c['date']).days) <= DIFFERENT_AMOUNT_MAX_DAYS
            and abs(l['amount'] - c['amount']) <= max(TOLERANCE, DIFFERENT_AMOUNT_MAX_RATIO * abs(c['amount']))
        ]
        if close:
            l = min(close, key=lambda l: (abs((l['date'] - c['date']).days), abs(l['amount'] - c['amount'])))
            only_ledger.remove(l)
            matches.append(([l], [c], STATUS_DIFFERENT_AMOUNT))
        else:
            matches.append(([], [c], STATUS_COMERCIAL_ONLY))
    matches.extend(([l], [], STATUS_CONTABILIDAD_ONLY) for l in only_ledger)
    return matches


def _folios_look_alike(a, b):
    """One digit different, or two neighbouring digits swapped."""
    a, b = str(int(a)), str(int(b))
    if len(a) != len(b):
        return False
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    return len(diff) == 1 or (
        len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]
    )


def _match_wrong_folios(pairs, facturas_by_id):
    """Joins a one-sided Comercial payment with a one-sided poliza on another
    invoice: same amount, a few days apart, folios that look alike. The row
    stays on the invoice Comercial applied the payment to; cited_invoice_id
    is the one the poliza names."""
    only_ledger = [p for p in pairs if p['status'] == STATUS_CONTABILIDAD_ONLY]
    for p in list(pairs):  # a copy: joined rows are removed from pairs below
        if p['status'] != STATUS_COMERCIAL_ONLY:
            continue
        c = p['comercial'][0]
        folio = facturas_by_id[p['invoice_id']]['CFOLIO']
        close = [
            q for q in only_ledger
            if q['invoice_id'] != p['invoice_id']
            and abs(q['ledger'][0]['amount'] - c['amount']) <= TOLERANCE
            and abs((q['ledger'][0]['date'] - c['date']).days) <= DIFFERENT_AMOUNT_MAX_DAYS
            and _folios_look_alike(folio, facturas_by_id[q['invoice_id']]['CFOLIO'])
        ]
        if close:
            q = min(close, key=lambda q: abs((q['ledger'][0]['date'] - c['date']).days))
            only_ledger.remove(q)
            pairs.remove(q)
            p.update(ledger=q['ledger'], status=STATUS_WRONG_FOLIO, cited_invoice_id=q['invoice_id'])
    return pairs


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

    pairs = [
        {'invoice_id': invoice_id, 'ledger': ledger_items, 'comercial': comercial_items,
         'status': status, 'cited_invoice_id': None}
        for invoice_id in ledger_by_invoice.keys() | comercial_by_invoice.keys()
        for ledger_items, comercial_items, status in pair_payments(
            ledger_by_invoice.get(invoice_id, []), comercial_by_invoice.get(invoice_id, []),
        )
    ]
    pairs = _match_wrong_folios(pairs, facturas_by_id)
    in_period = [
        p for p in pairs
        if any(date_from <= i['date'] <= date_to for i in p['ledger'] + p['comercial'])
    ]

    agent_codes = CommissionRepository.fetch_agent_codes()
    invoice_series = _invoice_series(
        {p['invoice_id'] for p in in_period} | {p['cited_invoice_id'] for p in in_period if p['cited_invoice_id']}
    )
    poliza_labels = CommissionRepository.fetch_poliza_labels(
        {pol for p in in_period for i in p['ledger'] for pol in i['polizas']}
    )

    rows = []
    for p in in_period:
        invoice_id, ledger_items, comercial_items, status = p['invoice_id'], p['ledger'], p['comercial'], p['status']
        cited = p['cited_invoice_id']
        factura = facturas_by_id[invoice_id]
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
            # folio_equivocado only: the invoice the poliza actually cites.
            'cited_invoice_id': cited,
            'cited_folio_display': (
                f"{invoice_series.get(cited, 'F')} {int(facturas_by_id[cited]['CFOLIO'])}" if cited else None
            ),
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

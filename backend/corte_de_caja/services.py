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
ledger payment resolution (the itemized per-invoice payment ledger - the
ONLY source of rows and dates here, see _payments_without_poliza for why)
and its CREFERENCIA matching - see that module for the full history of
getting this right. The one new piece here is emitting
EVERY dated payment installment in the window (an event log), not just the
single date an invoice finally reached zero balance the way commissions
needs - a partial abono is a real cash-collection event for this report even
though it isn't a commission-earning one for that report.
"""

from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count

from commissions.services import (
    GENERIC_CLIENT_PREFIX,
    LEDGER_FULL_PAYMENT_TOLERANCE,
    CommissionRepository,
    _classify_line,
    _extract_folio_tokens,
    attribute_ledger_payments,
)

from api.models import AdmConceptos, AdmDocumentos

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


BANK_CODES = ('BBVA', 'HSBC', 'BANAMEX', 'BANORTE')


def _bank_code(bank_name):
    """Short, stable bank key ('BBVA'...) from the ledger account name
    ('BBVA BANCOMER 0161357344'); '' when the bank isn't traceable."""
    name = (bank_name or '').upper()
    return next((code for code in BANK_CODES if code in name), '')


def _resolve_ledger_events(facturas, ledger_lines, concepto_series, bank_accounts, date_from, date_to):
    """Every dated, netted installment event the Contabilidad ledger records
    against a candidate Factura, restricted to [date_from, date_to] - built on
    the same attribution commissions uses (commissions.services.
    attribute_ledger_payments), but NOT collapsed to only the date the invoice
    reached full payment; a partial abono is its own event here. `abono` is
    set by walking the SAME cumulative-vs-CTOTAL logic, just keeping every
    step instead of only the one that clears the balance.

    Also resolves each event's bank (see _poliza_bank_accounts) and derives
    a suggested payment_method from it - only when every poliza netted into
    that date resolves to the SAME bank account, so a single event never
    mixes two different banks.

    Returns (events, covered_invoice_ids) - covered_invoice_ids lists every
    Factura the ledger resolves at least one real event for, ANYWHERE in
    [floor_date, today], not only within [date_from, date_to]. A Factura
    whose only ledger event falls outside this window is still "covered" -
    it correctly produces no row here, and is not listed as a payment
    without poliza either (see _payments_without_poliza).
    """
    poliza_bank = _poliza_bank_accounts(ledger_lines, bank_accounts)
    accepted = attribute_ledger_payments(facturas, ledger_lines, concepto_series)

    poliza_ref_accounts = defaultdict(set)  # accounts on each poliza's invoice-referenced lines (client + IVA)
    for id_poliza, referencia, fecha, concepto, importe, tipo_movto, id_cuenta in ledger_lines:
        if referencia:
            poliza_ref_accounts[id_poliza].add(id_cuenta)

    # Dated, netted events per invoice.
    events = []
    covered_invoice_ids = set()
    for f in facturas:
        by_date = accepted.get(f['CIDDOCUMENTO'])
        if not by_date:
            continue
        total = f['CTOTAL'] or 0
        cumulative = 0.0
        for event_date in sorted(by_date):
            entries = by_date[event_date]
            amount = sum(a for _, a in entries)
            polizas = {p for p, _ in entries}
            cumulative += amount
            # Netted entries carry the same few-cents rounding noise
            # LEDGER_FULL_PAYMENT_TOLERANCE already accounts for elsewhere
            # (see commissions.services) - found live 2026-09-24: a stray
            # -$0.02 "event" on an otherwise fully-settled invoice, not a
            # real collection.
            if abs(amount) < LEDGER_FULL_PAYMENT_TOLERANCE:
                continue
            # Covered as soon as the ledger resolves ANY real event for this
            # invoice, even one dated outside [date_from, date_to] - NOT only
            # when a resolved date happens to land inside the window. Found
            # 2026-09-26: querying a single day whose ONLY ledger-known
            # event fell one day earlier (the usual capture lag) wrongly
            # concluded "the ledger doesn't cover this" for that day and let
            # the Comercial fallback take over - which then showed a bulk,
            # multi-invoice payment as an approximate event on that day
            # instead of correctly showing no row at all (the real
            # collection is already accounted for on its actual date).
            covered_invoice_ids.add(f['CIDDOCUMENTO'])
            if date_from <= event_date <= date_to:
                accounts = {poliza_bank.get(p) for p in polizas}
                account_id = accounts.pop() if len(accounts) == 1 else None
                suggested_method, bank_name = _suggest_payment_method(account_id, bank_accounts)
                events.append({
                    'invoice_id': f['CIDDOCUMENTO'],
                    'factura': f,
                    'event_date': event_date,
                    'amount': _as_decimal(amount),
                    'abono': cumulative < total - LEDGER_FULL_PAYMENT_TOLERANCE,
                    'suggested_method': suggested_method,
                    'bank': bank_name,
                    'account_ids': sorted({a for p in polizas for a in poliza_ref_accounts.get(p, ())}),
                    'polizas': sorted(polizas),
                })
    return events, covered_invoice_ids


def _client_account_label(account_ids, client_account_codes):
    """The client's Contabilidad account as the accountant writes it in the
    CUENTA column (103-107-408): the payment poliza's referenced lines touch
    the client's account plus the IVA accounts, so keep only the '103' one.
    """
    for account_id in account_ids:
        code = client_account_codes.get(account_id)
        if code and code.isdigit() and len(code) == 9:
            return f'{code[0:3]}-{code[3:6]}-{code[6:9]}'
    return None


def _payments_without_poliza(facturas, payment_docs, ledger_covered_ids, date_from, date_to):
    """Payments Contpaqi Comercial records against a candidate Factura that
    the Contabilidad ledger has no poliza for at all - matched by the
    Comercial payment document's CREFERENCIA (same folio+client rule
    commissions' fallback uses).

    These are NOT cash-collection rows. Decided 2026-09-28: every date in
    this report must be the Contabilidad date, because Contabilidad is the
    audit record and SAT checks that dates on accounting documents match
    exactly - a row dated by Comercial would put a date on the corte that no
    poliza backs. Until 2026-09-28 they were shown as ordinary rows (and,
    when one Comercial payment named several invoices, with the full amount
    on each, flagged "approximate"). Now they are only listed so the
    accountant can register the poliza (or correct the reference) in
    Contpaqi; once the poliza exists the payment appears on its own date.

    Returns one dict per (payment document, matched invoice).
    """
    by_folio_client = defaultdict(list)
    for f in facturas:
        if f['CIDDOCUMENTO'] in ledger_covered_ids:
            continue
        by_folio_client[(int(f['CFOLIO']), f['CIDCLIENTEPROVEEDOR'])].append(f)

    payments = []
    for pago in payment_docs:
        comercial_date = pago['CFECHA'].date()
        if not (date_from <= comercial_date <= date_to):
            continue
        # Cents-sized documents are rounding leftovers, not collections
        # (same threshold the ledger events use).
        if abs(pago['CTOTAL'] or 0) < LEDGER_FULL_PAYMENT_TOLERANCE:
            continue
        cliente = pago['CIDCLIENTEPROVEEDOR']
        matched = []
        for token in _extract_folio_tokens(pago['CREFERENCIA']):
            matched.extend(by_folio_client.get((int(token), cliente), []))
        # A lone match that the payment couldn't fit into is the reference
        # pointing at the wrong invoice, not a missing poliza: found
        # 2026-09-28 on two cents-sized placeholder invoices (B 19975, B 19245)
        # sharing a folio number with the real, already-polized invoice the
        # payment was for (F 19975; 19179 in "19179 19245").
        if len(matched) == 1 and (pago['CTOTAL'] or 0) > (matched[0]['CTOTAL'] or 0) + LEDGER_FULL_PAYMENT_TOLERANCE:
            continue
        for f in matched:
            payments.append({
                'invoice_id': f['CIDDOCUMENTO'],
                'factura': f,
                'comercial_date': comercial_date,
                'amount': _as_decimal(pago['CTOTAL']),
                'referencia': pago['CREFERENCIA'],
                # The Comercial document carries one total for all the
                # invoices it names; only a poliza splits it per invoice.
                'shared_with': len(matched) - 1,
            })
    return payments


def _invoice_series(invoice_ids):
    """No. FACTURA on the real sheet is the tax series ('A', 'B', or 'F' for
    the default 16% series) plus the bare folio number. The series lives in
    AdmConceptos.CSERIEPOROMISION - CPREFIJOCONCEPTO is 'F' for every
    concept, so using it renders every B/A invoice as 'F' (verified against
    the accountant's Sep 2026 sheet: 272/273 rows match this way).
    """
    concepto_by_invoice = dict(
        AdmDocumentos.objects.filter(CIDDOCUMENTO__in=invoice_ids).values_list(
            'CIDDOCUMENTO', 'CIDCONCEPTODOCUMENTO',
        )
    )
    serie_by_concepto = dict(
        AdmConceptos.objects.values_list('CIDCONCEPTODOCUMENTO', 'CSERIEPOROMISION')
    )

    def display(concepto_id):
        serie = (serie_by_concepto.get(concepto_id) or '').strip().upper()
        return serie if serie in ('A', 'B') else 'F'

    return {
        invoice_id: display(concepto_id)
        for invoice_id, concepto_id in concepto_by_invoice.items()
    }


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


# --- Payment-method suggestion engine ---------------------------------------
# The ERP has no payment-method record and the receiving bank alone is a weak
# signal (checked on 3,715 payments tagged from the accountant's own sheet: the
# bank predicts the method only ~69% of the time), but each client's own
# confirmed history is strong. Tested chronologically (every payment predicted
# using only EARLIER days), same client + same bank with >= 3 earlier payments
# agreeing >= 80% was right 99% of the time on ~59% of payments; the same client
# at any bank (>= 4 payments) ~88% on another ~6%; everything else ~55%.
# History comes only from CONFIRMED tags (never from our own suggestions), so
# it can't feed on itself, and it keeps learning as accountants confirm rows.
SUGGESTION_MIN_PAYMENTS = 3
SUGGESTION_MIN_AGREEMENT = 0.8
CONFIDENCE_HIGH = 'alta'
CONFIDENCE_MEDIUM = 'media'
CONFIDENCE_LOW = 'baja'
PAYMENT_METHOD_LABELS = dict(CorteDeCajaAdjustment.PAYMENT_METHOD_CHOICES)


def _load_method_history():
    by_client_bank = defaultdict(Counter)
    by_client = defaultdict(Counter)
    tagged = (
        CorteDeCajaAdjustment.objects.exclude(payment_method='').exclude(client_id=None)
        .values('client_id', 'bank_code', 'payment_method').annotate(n=Count('id'))
    )
    for tag in tagged:
        by_client_bank[(tag['client_id'], tag['bank_code'])][tag['payment_method']] += tag['n']
        by_client[tag['client_id']][tag['payment_method']] += tag['n']
    return by_client_bank, by_client


def _predict_method(client_id, bank_code, client_name, history):
    """(method, confidence, plain-Spanish reason) from the client's confirmed
    history, or None when there isn't enough of it. The generic "Ventas Publico
    en General" client is skipped: many unrelated buyers share it."""
    if (client_name or '').upper().startswith(GENERIC_CLIENT_PREFIX):
        return None
    by_client_bank, by_client = history
    for counter, needed, confidence, scope in (
        (by_client_bank.get((client_id, bank_code)), SUGGESTION_MIN_PAYMENTS, CONFIDENCE_HIGH,
         'de este cliente en este banco'),
        (by_client.get(client_id), SUGGESTION_MIN_PAYMENTS + 1, CONFIDENCE_MEDIUM, 'de este cliente'),
    ):
        if not counter:
            continue
        total = sum(counter.values())
        if total < needed:
            continue
        method, hits = counter.most_common(1)[0]
        if hits / total >= SUGGESTION_MIN_AGREEMENT:
            return method, confidence, (
                f'{hits} de {total} pagos anteriores {scope} fueron {PAYMENT_METHOD_LABELS[method]}.'
            )
    return None


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
    without_poliza = _payments_without_poliza(facturas, payment_docs, ledger_covered_ids, date_from, date_to)

    all_events = ledger_events

    agent_codes = CommissionRepository.fetch_agent_codes()
    client_account_codes = CommissionRepository.fetch_client_account_codes()
    categories = _dominant_categories(list({e['invoice_id'] for e in all_events}))
    invoice_series = _invoice_series({e['invoice_id'] for e in all_events} | {p['invoice_id'] for p in without_poliza})
    adjustments = {
        (a.invoice_id, a.event_date): a for a in CorteDeCajaAdjustment.objects.filter(
            invoice_id__in={e['invoice_id'] for e in all_events}
        )
    }

    history = _load_method_history()
    suggestion_totals = {
        confidence: {'count': 0, 'total_amount': Decimal('0')}
        for confidence in (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW)
    }
    zone_totals = defaultdict(Decimal)
    method_totals = defaultdict(Decimal)
    rows = []
    unclassified_total = Decimal('0')
    unconfirmed_total = Decimal('0')

    for event in all_events:
        factura = event['factura']
        zone_code = agent_codes.get(factura['CIDAGENTE'])
        adjustment = adjustments.get((event['invoice_id'], event['event_date']))
        excluded = bool(adjustment and adjustment.excluded)
        manual_method = adjustment.payment_method if adjustment else ''
        # A human-confirmed tag always wins. Otherwise: the client's own
        # confirmed history when there's enough of it (see the engine above),
        # then the bank-derived suggestion (see _resolve_ledger_events) as a
        # low-confidence default - always unconfirmed, but populated, so the
        # day's totals are usable while the accountant works through the rest.
        confirmed = bool(manual_method)
        suggestion_confidence = None
        suggestion_reason = ''
        if manual_method:
            payment_method = manual_method
        else:
            prediction = _predict_method(
                factura['CIDCLIENTEPROVEEDOR'], _bank_code(event['bank']), factura['CRAZONSOCIAL'], history,
            )
            if prediction:
                payment_method, suggestion_confidence, suggestion_reason = prediction
            elif event['suggested_method']:
                payment_method = event['suggested_method']
                suggestion_confidence = CONFIDENCE_LOW
                suggestion_reason = 'Sin historial suficiente de este cliente: sugerido según el banco.'
            else:
                payment_method = ''

        if not excluded:
            zone_totals[zone_code] += event['amount']
            if payment_method:
                method_totals[payment_method] += event['amount']
                if not confirmed:
                    unconfirmed_total += event['amount']
                    suggestion_totals[suggestion_confidence]['count'] += 1
                    suggestion_totals[suggestion_confidence]['total_amount'] += event['amount']
            else:
                unclassified_total += event['amount']

        rows.append({
            'invoice_id': event['invoice_id'],
            'event_date': event['event_date'],
            'folio': factura['CFOLIO'],
            'folio_display': f"{invoice_series.get(event['invoice_id'], 'F')} {int(factura['CFOLIO'])}",
            'cliente': factura['CRAZONSOCIAL'],
            'zone': zone_code,
            'due_date': factura['CFECHAVENCIMIENTO'],
            'category': categories.get(event['invoice_id']),
            'amount': event['amount'],
            'abono': event['abono'],
            'excluded': excluded,
            'bank': event['bank'],
            'bank_code': _bank_code(event['bank']),
            'client_id': factura['CIDCLIENTEPROVEEDOR'],
            'cuenta': _client_account_label(event['account_ids'], client_account_codes),
            'payment_method': payment_method,
            'payment_method_confirmed': confirmed,
            'suggestion_confidence': suggestion_confidence,
            'suggestion_reason': suggestion_reason,
            'reviewed': bool(adjustment and adjustment.reviewed),
            'reviewed_by': adjustment.reviewed_by.username if adjustment and adjustment.reviewed_by else None,
            'note': adjustment.note if adjustment else '',
        })

    rows.sort(key=lambda r: (r['event_date'], r['zone'] or ''), reverse=False)

    sin_poliza_rows = sorted((
        {
            'invoice_id': p['invoice_id'],
            'comercial_date': p['comercial_date'],
            'folio_display': f"{invoice_series.get(p['invoice_id'], 'F')} {int(p['factura']['CFOLIO'])}",
            'client_id': p['factura']['CIDCLIENTEPROVEEDOR'],
            'cliente': p['factura']['CRAZONSOCIAL'],
            'zone': agent_codes.get(p['factura']['CIDAGENTE']),
            'invoice_date': p['factura']['CFECHA'].date(),
            'invoice_total': _as_decimal(p['factura']['CTOTAL']),
            'amount': p['amount'],
            'referencia': p['referencia'],
            'shared_with': p['shared_with'],
        }
        for p in without_poliza
    ), key=lambda r: (r['comercial_date'], r['folio_display']))

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
        'suggestions': suggestion_totals,
        'unconfirmed': {
            'count': len([r for r in rows if r['payment_method'] and not r['payment_method_confirmed'] and not r['excluded']]),
            'total_amount': unconfirmed_total,
            'note': (
                'Forma de pago sugerida automáticamente según el historial confirmado de cada cliente (o el '
                'banco, con confianza baja), aún sin confirmar por un usuario.'
            ),
        },
        'sin_poliza': {
            'count': len(sin_poliza_rows),
            'total_amount': sum((r['amount'] for r in sin_poliza_rows), Decimal('0')),
            'rows': sin_poliza_rows,
            'note': (
                'Pagos registrados en Contpaqi Comercial sin póliza en Contabilidad. No se incluyen en el corte: '
                'sus fechas deben venir de Contabilidad. Registre la póliza (o corrija la referencia) en Contpaqi '
                'y el pago aparecerá en la fecha de la póliza.'
            ),
        },
    }

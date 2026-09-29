"""Consulta de factura - everything the ERP knows about one invoice number,
on one screen.

Port of backend/scripts/consulta_factura.sql (tested by hand against
Contpaqi) into the platform. The point, per the accountants: Contpaqi seats
are license-limited, so not everyone who needs to check an invoice can open
Contpaqi at the same time.

Two things differ from the SQL script on purpose:
- Comercial payments come from admAsocCargosAbonos (the exact payment ->
  invoice record, see CommissionRepository.fetch_comercial_applications),
  not from the free-text CREFERENCIA. Payments whose reference mentions the
  folio but that Comercial applied somewhere else are still listed, with the
  invoice they were applied to - that's how a wrong folio shows up.
- Polizas are counted like the corte counts them (commissions.services.
  attribute_ledger_payments, pass 1): every payment poliza citing the
  invoice counts, unless the series+folio is shared with another invoice -
  then only polizas naming this client. The SQL's 12-character name filter
  hid real payments (F 20933).

Read-only, like everything else touching the ERP: SELECTs only. Client
names are returned live and never stored.
"""

import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db import connections

from commissions.services import (
    DEVOLUCION_DOC_TYPE,
    FACTURA_DOC_TYPE,
    LEDGER_DATABASE,
    LEDGER_FULL_PAYMENT_TOLERANCE,
    LEDGER_INGRESOS_TIPOPOL,
    LEDGER_PAGO_CONCEPTO,
    NOTA_CREDITO_DOC_TYPE,
    PAGO_CLIENTE_DOC_TYPE,
    PAGO_DOC_TYPES,
    _extract_folio_tokens,
    _normalize_name,
)
from corte_de_caja.date_differences import (
    STATUS_COMERCIAL_ONLY,
    STATUS_CONTABILIDAD_ONLY,
    DIFFERENT_AMOUNT_MAX_DAYS,
    STATUS_DIFFERENT_AMOUNT,
    STATUS_DIFFERENT_MONTH,
    STATUS_WRONG_FOLIO,
    pair_payments,
)
from corte_de_caja.services import BANK_ACCOUNT_CODE_PREFIX, CASH_ACCOUNT_CODE_PREFIX, _as_decimal

TOLERANCE = Decimal(str(LEDGER_FULL_PAYMENT_TOLERANCE))
CREDIT_DOC_TYPES = (NOTA_CREDITO_DOC_TYPE, DEVOLUCION_DOC_TYPE)

# "F 20933", "F-20933", "f20933", "20933" - the series is optional.
QUERY_RE = re.compile(r'^\s*([A-Za-z]?)\s*-?\s*(\d{1,7})\s*$')

# Same rule as corte_de_caja.services._invoice_series: the tax series lives
# in admConceptos.CSERIEPOROMISION; anything but A/B is the 16% 'F' series.
SERIES_SQL = "CASE WHEN c.CSERIEPOROMISION IN ('A','B') THEN c.CSERIEPOROMISION ELSE 'F' END"

# A payment poliza dated this long before the invoice cites an older invoice
# with the same number (F 19417 is cited by 2017 polizas) - same window the
# corte uses for its candidate invoices.
OLD_POLIZA_DAYS = 365

FLAG_ERROR = 'error'
FLAG_WARNING = 'warning'
FLAG_INFO = 'info'


def parse_query(text):
    """(series or None, folio) from what the user typed, or None."""
    match = QUERY_RE.match(text or '')
    if not match:
        return None
    return (match.group(1).upper() or None), int(match.group(2))


def _rows(sql, params):
    with connections['erp'].cursor() as cursor:
        cursor.execute(sql, params)
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _day(value):
    return value.date() if value else None


def _money(value):
    return _as_decimal(value or 0) + 0  # + 0 turns a rounded -0.00 into 0.00


class InvoiceRepository:
    @staticmethod
    def search(series, folio):
        """Every Factura with this folio, any series, cancelled or not."""
        return _rows(
            f"""
            SELECT d.CIDDOCUMENTO, {SERIES_SQL} AS serie, d.CFOLIO, d.CFECHA, d.CIDCLIENTEPROVEEDOR,
                   d.CRAZONSOCIAL, d.CTOTAL, d.CPENDIENTE, d.CCANCELADO, ag.CCODIGOAGENTE
            FROM admDocumentos d
            JOIN admConceptos c ON c.CIDCONCEPTODOCUMENTO = d.CIDCONCEPTODOCUMENTO
            LEFT JOIN admAgentes ag ON ag.CIDAGENTE = d.CIDAGENTE
            WHERE d.CIDDOCUMENTODE = %s AND d.CFOLIO = %s
            ORDER BY d.CFECHA DESC
            """,
            [FACTURA_DOC_TYPE, folio],
        )

    @staticmethod
    def fetch_invoice(invoice_id):
        rows = _rows(
            f"""
            SELECT d.CIDDOCUMENTO, {SERIES_SQL} AS serie, d.CFOLIO, d.CFECHA, d.CFECHAVENCIMIENTO,
                   d.CIDCLIENTEPROVEEDOR, d.CRAZONSOCIAL, d.CRFC, ag.CCODIGOAGENTE, ag.CNOMBREAGENTE,
                   d.CTOTAL, d.CPENDIENTE, d.CCANCELADO, d.CUSUARIO, d.CREFERENCIA, d.COBSERVACIONES
            FROM admDocumentos d
            JOIN admConceptos c ON c.CIDCONCEPTODOCUMENTO = d.CIDCONCEPTODOCUMENTO
            LEFT JOIN admAgentes ag ON ag.CIDAGENTE = d.CIDAGENTE
            WHERE d.CIDDOCUMENTO = %s AND d.CIDDOCUMENTODE = %s
            """,
            [invoice_id, FACTURA_DOC_TYPE],
        )
        return rows[0] if rows else None

    @staticmethod
    def fetch_lines(invoice_id):
        return _rows(
            """
            SELECT m.CNUMEROMOVIMIENTO, p.CCODIGOPRODUCTO, p.CNOMBREPRODUCTO, m.CUNIDADES, m.CPRECIO,
                   m.CDESCUENTO1 + m.CDESCUENTO2 + m.CDESCUENTO3 + m.CDESCUENTO4 + m.CDESCUENTO5 AS descuento,
                   m.CNETO, m.CIMPUESTO1, m.CTOTAL
            FROM admMovimientos m
            LEFT JOIN admProductos p ON p.CIDPRODUCTO = m.CIDPRODUCTO
            WHERE m.CIDDOCUMENTO = %s
            ORDER BY m.CNUMEROMOVIMIENTO
            """,
            [invoice_id],
        )

    @staticmethod
    def fetch_applications(invoice_id):
        """What Comercial applied to this invoice: customer payments, credit
        notes and returns, each with the amount applied to THIS invoice."""
        return _rows(
            """
            SELECT ab.CIDDOCUMENTO, ab.CIDDOCUMENTODE, dm.CDESCRIPCION, LTRIM(RTRIM(ab.CSERIEDOCUMENTO)) AS serie,
                   ab.CFOLIO, ab.CFECHA, a.CFECHAABONOCARGO, a.CIMPORTEABONO, ab.CTOTAL, ab.CCANCELADO,
                   ab.CREFERENCIA, ab.CUSUARIO
            FROM admAsocCargosAbonos a
            JOIN admDocumentos ab ON ab.CIDDOCUMENTO = a.CIDDOCUMENTOABONO
            JOIN admDocumentosModelo dm ON dm.CIDDOCUMENTODE = ab.CIDDOCUMENTODE
            WHERE a.CIDDOCUMENTOCARGO = %s
            ORDER BY ab.CFECHA, ab.CIDDOCUMENTO
            """,
            [invoice_id],
        )

    @staticmethod
    def fetch_linked_returns(invoice_id):
        """Returns/credit notes created from this invoice (CIDDOCUMENTOORIGEN),
        applied or not."""
        return _rows(
            """
            SELECT x.CIDDOCUMENTO, x.CIDDOCUMENTODE, dm.CDESCRIPCION, LTRIM(RTRIM(x.CSERIEDOCUMENTO)) AS serie,
                   x.CFOLIO, x.CFECHA, x.CTOTAL, x.CCANCELADO
            FROM admDocumentos x
            JOIN admDocumentosModelo dm ON dm.CIDDOCUMENTODE = x.CIDDOCUMENTODE
            WHERE x.CIDDOCUMENTOORIGEN = %s AND x.CIDDOCUMENTODE <> %s
            ORDER BY x.CFECHA
            """,
            [invoice_id, FACTURA_DOC_TYPE],
        )

    @staticmethod
    def fetch_client_payments(client_id):
        """The client's payment documents with a reference text, and the
        invoices Comercial applied each one to (may be none)."""
        return _rows(
            f"""
            SELECT pg.CIDDOCUMENTO, dm.CDESCRIPCION, LTRIM(RTRIM(pg.CSERIEDOCUMENTO)) AS serie, pg.CFOLIO,
                   pg.CFECHA, pg.CTOTAL, pg.CREFERENCIA, pg.CCANCELADO,
                   a.CIDDOCUMENTOCARGO, {SERIES_SQL} AS cargo_serie, f.CFOLIO AS cargo_folio
            FROM admDocumentos pg
            JOIN admDocumentosModelo dm ON dm.CIDDOCUMENTODE = pg.CIDDOCUMENTODE
            LEFT JOIN admAsocCargosAbonos a ON a.CIDDOCUMENTOABONO = pg.CIDDOCUMENTO
            LEFT JOIN admDocumentos f ON f.CIDDOCUMENTO = a.CIDDOCUMENTOCARGO
            LEFT JOIN admConceptos c ON c.CIDCONCEPTODOCUMENTO = f.CIDCONCEPTODOCUMENTO
            WHERE pg.CIDCLIENTEPROVEEDOR = %s AND pg.CIDDOCUMENTODE IN ({', '.join(['%s'] * len(PAGO_DOC_TYPES))})
              AND pg.CREFERENCIA IS NOT NULL AND pg.CREFERENCIA <> ''
            """,
            [client_id, *PAGO_DOC_TYPES],
        )

    @staticmethod
    def fetch_poliza_lines(series, folio):
        """Every line of every poliza with at least one line citing
        "{series}-{folio}" or "{series} {folio}" - the two forms the ledger
        uses (see attribute_ledger_payments)."""
        return _rows(
            f"""
            WITH citing AS (
                SELECT DISTINCT IdPoliza FROM {LEDGER_DATABASE}.dbo.MovimientosPoliza
                WHERE LTRIM(RTRIM(Referencia)) IN (%s, %s)
            )
            SELECT p.Id AS poliza_id, tp.Nombre AS tipo, p.TipoPol, p.Folio AS poliza_folio, p.Fecha AS poliza_fecha,
                   p.Concepto AS poliza_concepto, mp.NumMovto, cu.Codigo, cu.Nombre AS cuenta, mp.TipoMovto,
                   mp.Importe, LTRIM(RTRIM(mp.Referencia)) AS referencia, mp.Concepto
            FROM citing
            JOIN {LEDGER_DATABASE}.dbo.Polizas p ON p.Id = citing.IdPoliza
            JOIN {LEDGER_DATABASE}.dbo.TiposPolizas tp ON tp.Id = p.TipoPol
            JOIN {LEDGER_DATABASE}.dbo.MovimientosPoliza mp ON mp.IdPoliza = p.Id
            JOIN {LEDGER_DATABASE}.dbo.Cuentas cu ON cu.Id = mp.IdCuenta
            ORDER BY p.Fecha, p.Id, mp.NumMovto
            """,
            [f'{series}-{folio}', f'{series} {folio}'],
        )

    @staticmethod
    def fetch_collection_lines_citing(references, date_from, date_to):
        """Lines of collection polizas dated in the window that cite any of
        these references (see _wrong_folio_hints)."""
        return _rows(
            f"""
            SELECT p.Id AS poliza_id, tp.Nombre AS tipo, p.Folio AS poliza_folio, p.Fecha AS poliza_fecha,
                   LTRIM(RTRIM(mp.Referencia)) AS referencia, mp.TipoMovto, mp.Importe
            FROM {LEDGER_DATABASE}.dbo.MovimientosPoliza mp
            JOIN {LEDGER_DATABASE}.dbo.Polizas p ON p.Id = mp.IdPoliza
            JOIN {LEDGER_DATABASE}.dbo.TiposPolizas tp ON tp.Id = p.TipoPol
            WHERE LTRIM(RTRIM(mp.Referencia)) IN ({', '.join(['%s'] * len(references))})
              AND (p.Concepto = %s OR p.TipoPol = %s) AND p.Fecha BETWEEN %s AND %s
            """,
            [*references, LEDGER_PAGO_CONCEPTO, LEDGER_INGRESOS_TIPOPOL, date_from, date_to],
        )

    @staticmethod
    def fetch_cash_applications_to_folios(folios, date_from, date_to):
        """Customer payments dated in the window that Comercial applied to a
        non-cancelled Factura with one of these folios, any series."""
        return _rows(
            f"""
            SELECT f.CIDDOCUMENTO, {SERIES_SQL} AS factura_serie, f.CFOLIO, f.CFECHA, f.CRAZONSOCIAL,
                   LTRIM(RTRIM(ab.CSERIEDOCUMENTO)) AS serie, ab.CFOLIO AS pago_folio, ab.CFECHA AS pago_fecha,
                   a.CIMPORTEABONO
            FROM admAsocCargosAbonos a
            JOIN admDocumentos ab ON ab.CIDDOCUMENTO = a.CIDDOCUMENTOABONO
            JOIN admDocumentos f ON f.CIDDOCUMENTO = a.CIDDOCUMENTOCARGO
            JOIN admConceptos c ON c.CIDCONCEPTODOCUMENTO = f.CIDCONCEPTODOCUMENTO
            WHERE f.CIDDOCUMENTODE = %s AND f.CCANCELADO = 0 AND f.CFOLIO IN ({', '.join(['%s'] * len(folios))})
              AND ab.CIDDOCUMENTODE = %s AND ab.CCANCELADO = 0 AND ab.CFECHA BETWEEN %s AND %s
            """,
            [FACTURA_DOC_TYPE, *folios, PAGO_CLIENTE_DOC_TYPE, date_from, date_to],
        )


def search_invoices(text):
    """Invoices matching what the user typed. The series, when given, only
    orders the results: the same folio in another series is still listed,
    since a wrong series is one of the mistakes being looked for."""
    parsed = parse_query(text)
    if not parsed:
        return None
    series, folio = parsed
    results = [
        {
            'invoice_id': r['CIDDOCUMENTO'],
            'folio_display': f"{r['serie']} {int(r['CFOLIO'])}",
            'series_match': series is None or r['serie'] == series,
            'fecha': _day(r['CFECHA']),
            'client_id': r['CIDCLIENTEPROVEEDOR'],
            'cliente': r['CRAZONSOCIAL'],
            'zona': r['CCODIGOAGENTE'],
            'total': _money(r['CTOTAL']),
            'pendiente': _money(r['CPENDIENTE']),
            'cancelada': bool(r['CCANCELADO']),
        }
        for r in InvoiceRepository.search(series, folio)
    ]
    results.sort(key=lambda r: not r['series_match'])
    return results


def _document_label(serie, folio):
    return ' '.join(filter(None, [serie, str(int(folio or 0))]))


def not_counted_reason(is_payment, poliza_date, invoice_date, shared_reference, names_client):
    """Why a poliza citing an invoice does NOT count as a collection on it,
    or '' when it counts. The one rule for the invoice detail and the client
    history, so both show the same amounts."""
    if not is_payment:
        return 'No es una póliza de cobro.'
    if (invoice_date - poliza_date).days > OLD_POLIZA_DAYS:
        return 'Es de más de un año antes que la factura: cita otra factura con el mismo número.'
    if shared_reference and not names_client:
        return 'Otra factura tiene la misma serie y folio y esta póliza no menciona a este cliente.'
    return ''


def _polizas(lines, invoice, series, folio, shared_reference):
    """Groups the ledger lines per poliza and decides which polizas count as
    a collection on this invoice."""
    references = {f'{series}-{folio}'.upper(), f'{series} {folio}'.upper()}
    client_name = _normalize_name(invoice['CRAZONSOCIAL'])
    by_poliza = {}
    for line in lines:
        pid = line['poliza_id']
        if pid not in by_poliza:
            by_poliza[pid] = {
                'poliza_id': pid,
                'label': f"{line['tipo']} {line['poliza_folio']}",
                'fecha': _day(line['poliza_fecha']),
                'concepto': (line['poliza_concepto'] or '').strip(),
                'is_payment': (line['poliza_concepto'] or '').strip() == LEDGER_PAGO_CONCEPTO
                or line['TipoPol'] == LEDGER_INGRESOS_TIPOPOL,
                'lines': [],
            }
        cites = (line['referencia'] or '').upper() in references
        codigo = (line['Codigo'] or '').strip()
        by_poliza[pid]['lines'].append({
            'numero': line['NumMovto'],
            'codigo': codigo,
            'cuenta': (line['cuenta'] or '').strip(),
            'tipo': 'Abono' if line['TipoMovto'] else 'Cargo',
            'importe': _money(line['Importe']),
            'referencia': line['referencia'] or '',
            'concepto': (line['Concepto'] or '').strip(),
            'cites_invoice': cites,
            'is_bank': not line['referencia'] and not line['TipoMovto']
            and (codigo.startswith(CASH_ACCOUNT_CODE_PREFIX) or codigo.startswith(BANK_ACCOUNT_CODE_PREFIX)),
            '_signed': (line['Importe'] or 0) * (1 if line['TipoMovto'] else -1),
            '_names_client': bool(client_name) and client_name in _normalize_name(line['Concepto']),
        })

    polizas = []
    for p in by_poliza.values():
        citing = [line for line in p['lines'] if line['cites_invoice']]
        names_client = any(line['_names_client'] for line in citing)
        p['amount'] = _money(sum(line['_signed'] for line in citing))
        p['names_client'] = names_client
        p['bank'] = next((line['cuenta'] for line in p['lines'] if line['is_bank']), None)
        p['not_counted_reason'] = not_counted_reason(
            p['is_payment'], p['fecha'], invoice['CFECHA'].date(), shared_reference, names_client,
        )
        p['counted'] = not p['not_counted_reason']
        for line in p['lines']:
            del line['_signed'], line['_names_client']
        polizas.append(p)
    return polizas


def _payment_pairs(polizas, cash_applications):
    """Comercial payments next to their polizas, paired the way the
    "Discrepancias" tab pairs them (same amount, nearest date; pieces
    of one payment on one side only). One item per poliza, not netted per day
    like the corte: a duplicated poliza (B 20016, two identical 35,060
    polizas the same day) then pairs once and the copy is left on its own."""
    ledger = [
        {'date': p['fecha'], 'amount': p['amount'], 'polizas': [p['label']]}
        for p in polizas if p['counted'] and abs(p['amount']) >= TOLERANCE
    ]
    comercial = [
        {'date': a['fecha'], 'applied_date': a['applied_date'], 'amount': a['amount'], 'documento': a['documento']}
        for a in cash_applications if abs(a['amount']) >= TOLERANCE
    ]
    matches = pair_payments(ledger, comercial)

    pairs = []
    for ledger_items, comercial_items, status in matches:
        pairs.append({
            'status': status,
            'comercial': [
                {k: i[k] for k in ('date', 'applied_date', 'amount', 'documento')}
                for i in sorted(comercial_items, key=lambda i: i['date'])
            ],
            'contabilidad': [
                {k: i[k] for k in ('date', 'amount', 'polizas')}
                for i in sorted(ledger_items, key=lambda i: i['date'])
            ],
            # folio_equivocado only, see _wrong_folio_hints.
            'cited': None,
        })
    pairs.sort(key=lambda p: min(i['date'] for i in p['comercial'] + p['contabilidad']))
    return pairs


def _look_alike_folios(folio):
    """Every folio one digit away, or with two neighbouring digits swapped
    (date_differences._folios_look_alike, generated instead of tested)."""
    s = str(folio)
    out = {s[:i] + d + s[i + 1:] for i in range(len(s)) for d in '0123456789'}
    out |= {s[:i] + s[i + 1] + s[i] + s[i + 2:] for i in range(len(s) - 1)}
    return sorted(int(x) for x in out if x != s and not x.startswith('0'))


def _wrong_folio_hints(pairs, folio):
    """The dialog's side of the Discrepancias tab's "folio equivocado": a
    payment here with no poliza, and a poliza citing a look-alike folio for
    the same amount a few days apart that the other invoice has no payment
    for (or the reverse). Marks the pair and records the other side in
    pair['cited']."""
    lonely = [p for p in pairs if p['status'] in (STATUS_COMERCIAL_ONLY, STATUS_CONTABILIDAD_ONLY)]
    if not lonely:
        return
    folios = _look_alike_folios(folio)
    dates = [i['date'] for p in lonely for i in p['comercial'] + p['contabilidad']]
    window = (min(dates) - timedelta(days=DIFFERENT_AMOUNT_MAX_DAYS), max(dates) + timedelta(days=DIFFERENT_AMOUNT_MAX_DAYS))

    def near(a, b):
        return abs((a - b).days) <= DIFFERENT_AMOUNT_MAX_DAYS

    def same(a, b):
        return abs(a - b) <= TOLERANCE

    if any(p['status'] == STATUS_COMERCIAL_ONLY for p in lonely):
        references = {f'{s}{sep}{f}': (s, f) for s in ('F', 'A', 'B') for f in folios for sep in ('-', ' ')}
        citing = {}
        for line in InvoiceRepository.fetch_collection_lines_citing(list(references), *window):
            entry = citing.setdefault((line['poliza_id'], line['referencia'].upper()), {
                'label': f"{line['tipo']} {line['poliza_folio']}",
                'date': _day(line['poliza_fecha']),
                'amount': Decimal('0'),
                'cites': references[line['referencia'].upper()],
            })
            entry['amount'] += _money(line['Importe']) * (1 if line['TipoMovto'] else -1)
        for p in lonely:
            if p['status'] != STATUS_COMERCIAL_ONLY:
                continue
            c = p['comercial'][0]
            for e in sorted(citing.values(), key=lambda e: abs((e['date'] - c['date']).days)):
                if not (same(e['amount'], c['amount']) and near(e['date'], c['date'])):
                    continue
                serie, other_folio = e['cites']
                other = next((r for r in InvoiceRepository.search(serie, other_folio)
                              if r['serie'] == serie and not r['CCANCELADO']), None)
                if other is None or any(
                    a['CIDDOCUMENTODE'] == PAGO_CLIENTE_DOC_TYPE and not a['CCANCELADO']
                    and same(_money(a['CIMPORTEABONO']), c['amount']) and near(_day(a['CFECHA']), e['date'])
                    for a in InvoiceRepository.fetch_applications(other['CIDDOCUMENTO'])
                ):
                    continue
                p['status'] = STATUS_WRONG_FOLIO
                p['cited'] = {'invoice_id': other['CIDDOCUMENTO'], 'folio_display': f'{serie} {other_folio}',
                              'documento': f"Póliza {e['label']}", 'date': e['date'], 'amount': e['amount']}
                break

    if any(p['status'] == STATUS_CONTABILIDAD_ONLY for p in lonely):
        applied = InvoiceRepository.fetch_cash_applications_to_folios(folios, *window)
        for p in lonely:
            if p['status'] != STATUS_CONTABILIDAD_ONLY:
                continue
            l = p['contabilidad'][0]
            for r in sorted(applied, key=lambda r: abs((_day(r['pago_fecha']) - l['date']).days)):
                amount, paid = _money(r['CIMPORTEABONO']), _day(r['pago_fecha'])
                if not (same(amount, l['amount']) and near(paid, l['date'])):
                    continue
                serie, other_folio = r['factura_serie'], int(r['CFOLIO'])
                other_polizas = _polizas(
                    InvoiceRepository.fetch_poliza_lines(serie, other_folio), r, serie, other_folio, False,
                )
                if any(q['counted'] and same(q['amount'], amount) and near(q['fecha'], paid) for q in other_polizas):
                    continue
                p['status'] = STATUS_WRONG_FOLIO
                p['cited'] = {'invoice_id': r['CIDDOCUMENTO'], 'folio_display': f'{serie} {other_folio}',
                              'documento': _document_label(r['serie'], r['pago_folio']), 'date': paid, 'amount': amount}
                break


def _currency(value):
    return f'${value:,.2f}'


def _flags(invoice, balance, pairs, applications, referencing_payments, same_folio, polizas):
    """Things to fix in Contpaqi, most serious first."""
    flags = []
    total = balance['total']
    cancelled = invoice['cancelada']

    if cancelled and (balance['comercial_cash'] >= TOLERANCE or balance['contabilidad_cash'] >= TOLERANCE):
        flags.append((FLAG_ERROR, 'La factura está CANCELADA pero tiene pagos o cobros registrados.'))
    if balance['contabilidad_cash'] > total + TOLERANCE:
        flags.append((FLAG_ERROR, (
            f"Contabilidad registra {_currency(balance['contabilidad_cash'])} de cobro, más que el total de la "
            f"factura ({_currency(total)}): póliza duplicada o que cita un folio equivocado."
        )))
    for pair in pairs:
        if pair['status'] == STATUS_DIFFERENT_MONTH:
            comercial_dates = ', '.join(i['date'].strftime('%d/%m/%Y') for i in pair['comercial'])
            ledger_dates = ', '.join(i['date'].strftime('%d/%m/%Y') for i in pair['contabilidad'])
            flags.append((FLAG_ERROR, (
                f'Pago en Comercial el {comercial_dates} y póliza el {ledger_dates}: '
                'se declaran en meses distintos.'
            )))
    # The per-payment flags below already say where the difference is; this
    # one is for a difference no single payment explains.
    unpaired = any(p['status'] in (
        STATUS_COMERCIAL_ONLY, STATUS_CONTABILIDAD_ONLY, STATUS_DIFFERENT_AMOUNT, STATUS_WRONG_FOLIO,
    ) for p in pairs)
    if not cancelled and not unpaired and abs(balance['comercial_cash'] - balance['contabilidad_cash']) > TOLERANCE:
        flags.append((FLAG_WARNING, (
            f"Comercial registra {_currency(balance['comercial_cash'])} en pagos del cliente y Contabilidad "
            f"{_currency(balance['contabilidad_cash'])} en pólizas de cobro."
        )))
    for pair in pairs:
        if pair['status'] == STATUS_COMERCIAL_ONLY:
            c = pair['comercial'][0]
            flags.append((FLAG_WARNING, (
                f"El pago {c['documento']} del {c['date']:%d/%m/%Y} por {_currency(c['amount'])} "
                'no tiene póliza en Contabilidad.'
            )))
        elif pair['status'] == STATUS_WRONG_FOLIO and pair['comercial']:
            c, cited = pair['comercial'][0], pair['cited']
            flags.append((FLAG_WARNING, (
                f"El pago {c['documento']} del {c['date']:%d/%m/%Y} por {_currency(c['amount'])} no tiene póliza "
                f"que cite esta factura, pero la {cited['documento']} del {cited['date']:%d/%m/%Y} por el mismo "
                f"monto cita {cited['folio_display']}: posible folio equivocado en la póliza."
            )))
        elif pair['status'] == STATUS_WRONG_FOLIO:
            l, cited = pair['contabilidad'][0], pair['cited']
            flags.append((FLAG_WARNING, (
                f"La póliza {', '.join(l['polizas'])} del {l['date']:%d/%m/%Y} por {_currency(l['amount'])} cita "
                f"esta factura, pero en Comercial ese monto es el pago {cited['documento']} del "
                f"{cited['date']:%d/%m/%Y} aplicado a {cited['folio_display']}: posible folio equivocado en la póliza."
            )))
        elif pair['status'] == STATUS_DIFFERENT_AMOUNT:
            c, l = pair['comercial'][0], pair['contabilidad'][0]
            flags.append((FLAG_WARNING, (
                f"El pago {c['documento']} del {c['date']:%d/%m/%Y} es por {_currency(c['amount'])} en Comercial, "
                f"pero la póliza {', '.join(l['polizas'])} del {l['date']:%d/%m/%Y} es por {_currency(l['amount'])}."
            )))
        elif pair['status'] == STATUS_CONTABILIDAD_ONLY:
            l = pair['contabilidad'][0]
            twin = next((
                p['label'] for p in polizas
                if p['counted'] and p['label'] not in l['polizas'] and p['fecha'] == l['date'] and p['amount'] == l['amount']
            ), None)
            flags.append((FLAG_WARNING, (
                f"La póliza {', '.join(l['polizas'])} del {l['date']:%d/%m/%Y} por {_currency(l['amount'])} "
                + (f'repite la fecha y el importe de la póliza {twin}: posible póliza duplicada.' if twin
                   else 'no tiene un pago aplicado en Comercial por ese monto.')
            )))
    applied_sum = sum((a['amount'] for a in applications), Decimal('0'))
    if not cancelled and abs(applied_sum - balance['pagado_comercial']) > TOLERANCE:
        flags.append((FLAG_WARNING, (
            f"Comercial marca {_currency(balance['pagado_comercial'])} como pagado, pero los documentos "
            f"aplicados suman {_currency(applied_sum)}."
        )))
    early = [a for a in applications if a['fecha'] and a['fecha'] < invoice['fecha']]
    if early:
        flags.append((FLAG_INFO, (
            f"{len(early)} documento(s) aplicado(s) están fechados antes que la factura "
            f"({', '.join(a['documento'] for a in early)}): un anticipo, o un pago con la referencia equivocada."
        )))
    for p in referencing_payments:
        applied_to = ', '.join(p['applied_to']) or 'ninguna factura'
        flags.append((FLAG_INFO, (
            f"{p['tipo']} {p['documento']} del {p['fecha']:%d/%m/%Y} menciona este folio en su referencia, "
            f'pero Comercial lo aplicó a {applied_to}.'
        )))
    for p in polizas:
        if p['is_payment'] and not p['counted']:
            flags.append((FLAG_INFO, f"Póliza {p['label']} cita la factura, pero no se cuenta: {p['not_counted_reason']}"))
    same_series = [r for r in same_folio if r['folio_display'] == invoice['folio_display']]
    if same_series:
        flags.append((FLAG_INFO, (
            f"Hay {len(same_series)} factura(s) más con el mismo número {invoice['folio_display']}; "
            'revise que los pagos y pólizas sean de este cliente.'
        )))
    return [{'level': level, 'text': text} for level, text in flags]


def invoice_detail(invoice_id):
    row = InvoiceRepository.fetch_invoice(invoice_id)
    if not row:
        return None
    series = row['serie']
    folio = int(row['CFOLIO'])
    invoice = {
        'invoice_id': row['CIDDOCUMENTO'],
        'folio_display': f'{series} {folio}',
        'serie': series,
        'folio': folio,
        'fecha': _day(row['CFECHA']),
        'vencimiento': _day(row['CFECHAVENCIMIENTO']),
        'client_id': row['CIDCLIENTEPROVEEDOR'],
        'cliente': row['CRAZONSOCIAL'],
        'rfc': (row['CRFC'] or '').strip(),
        'zona': row['CCODIGOAGENTE'],
        'agente': (row['CNOMBREAGENTE'] or '').strip(),
        'total': _money(row['CTOTAL']),
        'pendiente': _money(row['CPENDIENTE']),
        'cancelada': bool(row['CCANCELADO']),
        'usuario': (row['CUSUARIO'] or '').strip(),
        'referencia': (row['CREFERENCIA'] or '').strip(),
        'observaciones': (row['COBSERVACIONES'] or '').strip(),
    }
    invoice['vencida'] = bool(
        not invoice['cancelada'] and invoice['pendiente'] >= TOLERANCE
        and invoice['vencimiento'] and invoice['vencimiento'] < date.today()
    )

    lines = [
        {
            'numero': int(l['CNUMEROMOVIMIENTO'] or 0),
            'codigo': (l['CCODIGOPRODUCTO'] or '').strip(),
            'producto': (l['CNOMBREPRODUCTO'] or '').strip(),
            'cantidad': l['CUNIDADES'],
            'precio': _money(l['CPRECIO']),
            'descuento': _money(l['descuento']),
            'neto': _money(l['CNETO']),
            'iva': _money(l['CIMPUESTO1']),
            'total': _money(l['CTOTAL']),
        }
        for l in InvoiceRepository.fetch_lines(invoice_id)
    ]

    applications = [
        {
            'documento_id': a['CIDDOCUMENTO'],
            'doc_type': a['CIDDOCUMENTODE'],
            'tipo': a['CDESCRIPCION'],
            'documento': _document_label(a['serie'], a['CFOLIO']),
            'fecha': _day(a['CFECHA']),
            'applied_date': _day(a['CFECHAABONOCARGO']),
            'amount': _money(a['CIMPORTEABONO']),
            'documento_total': _money(a['CTOTAL']),
            'cancelado': bool(a['CCANCELADO']),
            'referencia': (a['CREFERENCIA'] or '').strip(),
            'usuario': (a['CUSUARIO'] or '').strip(),
        }
        for a in InvoiceRepository.fetch_applications(invoice_id)
    ]
    applied_ids = {a['documento_id'] for a in applications}
    unapplied_returns = [
        {
            'documento_id': r['CIDDOCUMENTO'],
            'tipo': r['CDESCRIPCION'],
            'documento': _document_label(r['serie'], r['CFOLIO']),
            'fecha': _day(r['CFECHA']),
            'total': _money(r['CTOTAL']),
            'cancelado': bool(r['CCANCELADO']),
        }
        for r in InvoiceRepository.fetch_linked_returns(invoice_id)
        if r['CIDDOCUMENTO'] not in applied_ids
    ]

    # Payments whose reference text mentions this folio but that Comercial
    # applied elsewhere (or nowhere) - a likely wrong folio on one side.
    by_payment = {}
    for p in InvoiceRepository.fetch_client_payments(row['CIDCLIENTEPROVEEDOR']):
        if p['CIDDOCUMENTO'] in applied_ids or str(folio) not in _extract_folio_tokens(p['CREFERENCIA']):
            continue
        entry = by_payment.setdefault(p['CIDDOCUMENTO'], {
            'documento_id': p['CIDDOCUMENTO'],
            'tipo': p['CDESCRIPCION'],
            'documento': _document_label(p['serie'], p['CFOLIO']),
            'fecha': _day(p['CFECHA']),
            'total': _money(p['CTOTAL']),
            'referencia': (p['CREFERENCIA'] or '').strip(),
            'cancelado': bool(p['CCANCELADO']),
            'applied_to': [],
        })
        if p['CIDDOCUMENTOCARGO']:
            entry['applied_to'].append(_document_label(p['cargo_serie'], p['cargo_folio']))
    referencing_payments = sorted(
        (p for p in by_payment.values() if not p['cancelado']), key=lambda p: p['fecha'],
    )

    same_folio = [r for r in search_invoices(str(folio)) if r['invoice_id'] != invoice_id]
    shared_reference = any(
        r['folio_display'] == invoice['folio_display'] and not r['cancelada'] for r in same_folio
    )
    polizas = _polizas(InvoiceRepository.fetch_poliza_lines(series, folio), row, series, folio, shared_reference)

    cash_applications = [a for a in applications if a['doc_type'] == PAGO_CLIENTE_DOC_TYPE and not a['cancelado']]
    balance = {
        'total': invoice['total'],
        'pendiente': invoice['pendiente'],
        # Contpaqi zeroes CPENDIENTE when it cancels an invoice, so "total -
        # pendiente" would show a cancelled invoice as fully paid.
        'pagado_comercial': (
            sum((a['amount'] for a in applications if not a['cancelado']), Decimal('0'))
            if invoice['cancelada'] else invoice['total'] - invoice['pendiente']
        ),
        'comercial_cash': sum((a['amount'] for a in cash_applications), Decimal('0')),
        'comercial_credit': sum(
            (a['amount'] for a in applications if a['doc_type'] in CREDIT_DOC_TYPES and not a['cancelado']),
            Decimal('0'),
        ),
        'comercial_other': sum(
            (a['amount'] for a in applications
             if a['doc_type'] not in (PAGO_CLIENTE_DOC_TYPE, *CREDIT_DOC_TYPES) and not a['cancelado']),
            Decimal('0'),
        ),
        'contabilidad_cash': sum((p['amount'] for p in polizas if p['counted']), Decimal('0')),
        'polizas_de_cobro': sum(1 for p in polizas if p['counted']),
    }
    pairs = _payment_pairs(polizas, cash_applications)
    if not invoice['cancelada']:
        _wrong_folio_hints(pairs, folio)
    flags = _flags(invoice, balance, pairs, applications, referencing_payments, same_folio, polizas)
    balance['ok'] = not any(f['level'] in (FLAG_ERROR, FLAG_WARNING) for f in flags)

    return {
        'invoice': invoice,
        'lines': lines,
        'balance': balance,
        'flags': flags,
        'payments': pairs,
        'applications': applications,
        'unapplied_returns': unapplied_returns,
        'referencing_payments': referencing_payments,
        'polizas': polizas,
        'same_folio': same_folio,
    }

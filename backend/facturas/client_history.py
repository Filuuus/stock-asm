"""Historial de un cliente - every invoice of one client with how it was
paid, opened from any client name in the platform (the companion of the
invoice detail in services.py).

Per invoice it answers the questions the invoice detail answers one at a
time, in bulk: how much Comercial applied (money vs credit notes), how
much the Contabilidad payment polizas cover (same counting rule as the
detail, services.not_counted_reason), the date the polizas covered the
money part - the Contabilidad date, like the corte and commissions use -
and how late that was against the due date.

Read-only, like everything else touching the ERP. The client's name is
returned live and never stored.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from commissions.services import (
    FACTURA_DOC_TYPE,
    LEDGER_DATABASE,
    LEDGER_INGRESOS_TIPOPOL,
    LEDGER_PAGO_CONCEPTO,
    PAGO_CLIENTE_DOC_TYPE,
    _normalize_name,
)

from .services import SERIES_SQL, TOLERANCE, _day, _money, _rows, not_counted_reason

# Recent history shown by default; open invoices are always included,
# however old.
RECENT_DAYS = 365
# SQL Server caps a query at 2,100 parameters.
CHUNK = 900


def _chunks(items, size=CHUNK):
    items = list(items)
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _placeholders(items):
    return ', '.join(['%s'] * len(items))


class ClientRepository:
    @staticmethod
    def fetch_client(client_id):
        rows = _rows(
            """
            SELECT c.CIDCLIENTEPROVEEDOR, c.CCODIGOCLIENTE, c.CRAZONSOCIAL, c.CRFC, c.CFECHAALTA,
                   c.CDIASCREDITOCLIENTE, c.CLIMITECREDITOCLIENTE, c.CESTATUS, ag.CCODIGOAGENTE
            FROM admClientes c
            LEFT JOIN admAgentes ag ON ag.CIDAGENTE = c.CIDAGENTEVENTA
            WHERE c.CIDCLIENTEPROVEEDOR = %s
            """,
            [client_id],
        )
        return rows[0] if rows else None

    @staticmethod
    def fetch_invoices(client_id, since):
        """The client's invoices dated since `since` (None = all), plus every
        still-open one."""
        return _rows(
            f"""
            SELECT d.CIDDOCUMENTO, {SERIES_SQL} AS serie, d.CFOLIO, d.CFECHA, d.CFECHAVENCIMIENTO,
                   d.CTOTAL, d.CPENDIENTE, d.CCANCELADO, ag.CCODIGOAGENTE
            FROM admDocumentos d
            JOIN admConceptos c ON c.CIDCONCEPTODOCUMENTO = d.CIDCONCEPTODOCUMENTO
            LEFT JOIN admAgentes ag ON ag.CIDAGENTE = d.CIDAGENTE
            WHERE d.CIDDOCUMENTODE = %s AND d.CIDCLIENTEPROVEEDOR = %s
              AND (%s IS NULL OR d.CFECHA >= %s OR (d.CCANCELADO = 0 AND d.CPENDIENTE >= 1))
            ORDER BY d.CFECHA DESC, d.CFOLIO DESC
            """,
            [FACTURA_DOC_TYPE, client_id, since, since],
        )

    @staticmethod
    def fetch_applications(invoice_ids):
        """(invoice id, doc type, amount) for every non-cancelled document
        Comercial applied to these invoices."""
        rows = []
        for chunk in _chunks(invoice_ids):
            rows += _rows(
                f"""
                SELECT a.CIDDOCUMENTOCARGO, ab.CIDDOCUMENTODE, a.CIMPORTEABONO
                FROM admAsocCargosAbonos a
                JOIN admDocumentos ab ON ab.CIDDOCUMENTO = a.CIDDOCUMENTOABONO
                WHERE ab.CCANCELADO = 0 AND a.CIDDOCUMENTOCARGO IN ({_placeholders(chunk)})
                """,
                chunk,
            )
        return rows

    @staticmethod
    def fetch_shared_references(pairs):
        """The (series, folio) pairs among `pairs` that more than one
        non-cancelled invoice uses - any client."""
        folios = sorted({folio for _, folio in pairs})
        shared = set()
        for chunk in _chunks(folios):
            for r in _rows(
                f"""
                SELECT {SERIES_SQL} AS serie, CAST(d.CFOLIO AS int) AS folio
                FROM admDocumentos d
                JOIN admConceptos c ON c.CIDCONCEPTODOCUMENTO = d.CIDCONCEPTODOCUMENTO
                WHERE d.CIDDOCUMENTODE = %s AND d.CCANCELADO = 0 AND d.CFOLIO IN ({_placeholders(chunk)})
                GROUP BY {SERIES_SQL}, CAST(d.CFOLIO AS int)
                HAVING COUNT(*) > 1
                """,
                [FACTURA_DOC_TYPE, *chunk],
            ):
                shared.add((r['serie'], r['folio']))
        return shared & set(pairs)

    @staticmethod
    def fetch_citing_lines(references):
        """Lines of any poliza that cite one of `references` ("F-20933" /
        "F 20933"), with what's needed to decide whether the poliza counts.
        Joined against a VALUES list rather than `IN (...)`: SQL Server then
        reads MovimientosPoliza (~380k lines) once with a hash match - 0.2s
        instead of 2.5s for a client with 60 invoices."""
        rows = []
        for chunk in _chunks(sorted(set(references)), 2000):
            rows += _rows(
                f"""
                SELECT UPPER(LTRIM(RTRIM(mp.Referencia))) AS referencia, p.Id AS poliza_id, p.Fecha AS poliza_fecha,
                       p.Concepto AS poliza_concepto, p.TipoPol, mp.TipoMovto, mp.Importe, mp.Concepto
                FROM (VALUES {', '.join(['(%s)'] * len(chunk))}) v(ref)
                JOIN {LEDGER_DATABASE}.dbo.MovimientosPoliza mp ON LTRIM(RTRIM(mp.Referencia)) = v.ref
                JOIN {LEDGER_DATABASE}.dbo.Polizas p ON p.Id = mp.IdPoliza
                """,
                chunk,
            )
        return rows


def _ledger_by_invoice(invoices, client_name, shared, lines):
    """{invoice id: [(poliza date, amount), ...]} - the payment polizas that
    count for each invoice, netted per poliza like the invoice detail."""
    by_reference = defaultdict(list)
    for line in lines:
        by_reference[line['referencia']].append(line)

    result = {}
    for inv in invoices:
        series, folio = inv['serie'], int(inv['CFOLIO'])
        polizas = {}
        for reference in (f'{series}-{folio}', f'{series} {folio}'):
            for line in by_reference.get(reference, []):
                p = polizas.setdefault(line['poliza_id'], {
                    'fecha': _day(line['poliza_fecha']),
                    'is_payment': (line['poliza_concepto'] or '').strip() == LEDGER_PAGO_CONCEPTO
                    or line['TipoPol'] == LEDGER_INGRESOS_TIPOPOL,
                    'amount': 0.0,
                    'names_client': False,
                })
                p['amount'] += (line['Importe'] or 0) * (1 if line['TipoMovto'] else -1)
                p['names_client'] |= bool(client_name) and client_name in _normalize_name(line['Concepto'])
        result[inv['CIDDOCUMENTO']] = sorted(
            (p['fecha'], _money(p['amount']))
            for p in polizas.values()
            if not not_counted_reason(
                p['is_payment'], p['fecha'], inv['CFECHA'].date(), (series, folio) in shared, p['names_client'],
            )
        )
    return result


def client_history(client_id, full=False):
    client = ClientRepository.fetch_client(client_id)
    if not client:
        return None
    today = date.today()
    since = None if full else today - timedelta(days=RECENT_DAYS)
    invoices = ClientRepository.fetch_invoices(client_id, since)
    ids = [i['CIDDOCUMENTO'] for i in invoices]

    cash = defaultdict(Decimal)
    credit = defaultdict(Decimal)
    for a in ClientRepository.fetch_applications(ids):
        target = cash if a['CIDDOCUMENTODE'] == PAGO_CLIENTE_DOC_TYPE else credit
        target[a['CIDDOCUMENTOCARGO']] += _money(a['CIMPORTEABONO'])

    pairs = {(i['serie'], int(i['CFOLIO'])) for i in invoices}
    shared = ClientRepository.fetch_shared_references(pairs)
    references = [ref for s, f in pairs for ref in (f'{s}-{f}', f'{s} {f}')]
    ledger = _ledger_by_invoice(
        invoices, _normalize_name(client['CRAZONSOCIAL']), shared, ClientRepository.fetch_citing_lines(references),
    )

    rows = []
    for inv in invoices:
        invoice_id = inv['CIDDOCUMENTO']
        cancelled = bool(inv['CCANCELADO'])
        total = _money(inv['CTOTAL'])
        pending = _money(inv['CPENDIENTE'])
        due = _day(inv['CFECHAVENCIMIENTO'])
        polizas = ledger.get(invoice_id, [])
        contabilidad = sum((amount for _, amount in polizas), Decimal('0'))

        # The day the polizas covered the part paid with money (credit
        # notes have no payment poliza) - the date commissions use too.
        paid_date = None
        if not cancelled and pending < TOLERANCE and cash[invoice_id] >= TOLERANCE:
            running = Decimal('0')
            for poliza_date, amount in polizas:
                running += amount
                if running >= cash[invoice_id] - TOLERANCE:
                    paid_date = poliza_date
                    break

        if cancelled:
            status = 'cancelada'
        elif pending < TOLERANCE:
            status = 'pagada'
        elif due and due < today:
            status = 'vencida'
        else:
            status = 'pendiente'

        if paid_date and due:
            days_late = (paid_date - due).days
        elif status == 'vencida':
            days_late = (today - due).days
        else:
            days_late = None

        rows.append({
            'invoice_id': invoice_id,
            'folio_display': f"{inv['serie']} {int(inv['CFOLIO'])}",
            'fecha': _day(inv['CFECHA']),
            'vencimiento': due,
            'zona': inv['CCODIGOAGENTE'],
            'total': total,
            'pendiente': Decimal('0') if cancelled else pending,
            'comercial_cash': cash[invoice_id],
            'comercial_credit': credit[invoice_id],
            'contabilidad_cash': contabilidad,
            'paid_date': paid_date,
            'days_late': days_late,
            'status': status,
            # Same check as the "Cuadre" of the invoice detail; the detail
            # also compares each payment's date and amount.
            'cuadra': not (
                (cancelled and (cash[invoice_id] >= TOLERANCE or contabilidad >= TOLERANCE))
                or (not cancelled and abs(cash[invoice_id] - contabilidad) > TOLERANCE)
            ),
        })

    live = [r for r in rows if r['status'] != 'cancelada']
    recent = [r for r in live if since is None or r['fecha'] >= since]
    paid = [r for r in recent if r['paid_date'] and r['days_late'] is not None]
    overdue = [r for r in live if r['status'] == 'vencida']
    summary = {
        'since': since,
        'facturado': sum((r['total'] for r in recent), Decimal('0')),
        'facturas': len(recent),
        'saldo_pendiente': sum((r['pendiente'] for r in live), Decimal('0')),
        'facturas_pendientes': sum(1 for r in live if r['pendiente'] >= TOLERANCE),
        'vencido': sum((r['pendiente'] for r in overdue), Decimal('0')),
        'facturas_vencidas': len(overdue),
        'pagadas_con_fecha': len(paid),
        'pagadas_a_tiempo': sum(1 for r in paid if r['days_late'] <= 0),
        'promedio_dias_atraso': (
            round(sum(max(r['days_late'], 0) for r in paid) / len(paid), 1) if paid else None
        ),
        'no_cuadran': sum(1 for r in rows if not r['cuadra']),
    }

    return {
        'client': {
            'client_id': client['CIDCLIENTEPROVEEDOR'],
            'codigo': (client['CCODIGOCLIENTE'] or '').strip(),
            'cliente': client['CRAZONSOCIAL'],
            'rfc': (client['CRFC'] or '').strip(),
            'zona': client['CCODIGOAGENTE'],
            'dias_credito': client['CDIASCREDITOCLIENTE'],
            'limite_credito': _money(client['CLIMITECREDITOCLIENTE']),
            'alta': _day(client['CFECHAALTA']),
            'activo': client['CESTATUS'] == 1,
        },
        'summary': summary,
        'invoices': rows,
        'full': full,
    }

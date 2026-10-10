"""Rentabilidad: gross profit and kg by month, zone, client and product, for management to
slice by brand, category, salesperson or any mix of them.

Same sales rule as /ventas and Comisiones: Facturas (4) not cancelled, in the ZONE_SCOPE
zones, by invoice date, before IVA, cost = the ERP's CCOSTOESPECIFICO; returns (5) net in
the month issued. Credit notes (7) carry no product in this ERP (one "(Ninguno)" line), so
each one is spread over the lines of the invoices it was applied to (admAsocCargosAbonos),
pro rata by line amount, and dated in its own month; any unapplied part stays without a
product.

Advances are not sales here: the advance invoice (product ADVANCE_PRODUCT_CODE, no cost)
and the credit note that later applies it to the real invoice are both left out, so the real
invoice counts in full in its own month. Counting them spread the note over the real
invoice's products as a loss (checked 2026-10-10: most 2025 credit notes were advance
applications, e.g. F-19411 -> F-19456). Foreign-currency documents are converted to pesos at
their own exchange rate (the ERP keeps their amounts in dollars, costs in pesos).
Products management excludes (ExcludedProduct, one-off deals) are dropped with their returns
and credit notes. Punto de Venta invoices go to the route that owns the client (PuntoVentaClientZone),
as in the Bionat report. Read-only, like every ERP access in this project.

The ERP rows are cached per period; zones, categories and kg are worked out on each request,
so a weight typed in by management shows up at once.
"""
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from django.core.cache import cache
from django.db import connections

from commissions.services import (
    DEVOLUCION_DOC_TYPE,
    FACTURA_DOC_TYPE,
    NOTA_CREDITO_DOC_TYPE,
    PUNTOVENTA_ZONE_NAME,
    ZONE_SCOPE,
    CommissionRepository,
    _classify_line,
)

from .models import ExcludedProduct, ProductWeight
from .weights import estimate_kg, load_gea

CACHE_KEY = 'profitability_v2_{}_{}'  # bump the version when the cached shape changes
CACHE_SECONDS = 600
NO_BRAND = 'Sin marca'
SERVICE_PRODUCT_TYPE = 3
# Net in pesos: dollar documents keep their amounts in dollars.
NET = ('(m.CNETO - m.CDESCUENTO1 - m.CDESCUENTO2 - m.CDESCUENTO3 - m.CDESCUENTO4 - m.CDESCUENTO5)'
       ' * CASE WHEN d.CIDMONEDA = 1 THEN 1 ELSE d.CTIPOCAMBIO END')
NOTE_RATE = 'CASE WHEN n.CIDMONEDA = 1 THEN 1 ELSE n.CTIPOCAMBIO END'
ADVANCE_PRODUCT_CODE = '84111506'  # SAT key "anticipo"; ERP name "ANTICIPO APLICABLE A FACTURA"
# "APLICACION DE ANTICIPO DE LA F-19411 A LA F-19456", or without the word: "DE LA F-17367 APLICA F-18153".
ADVANCE_FOLIO_RE = re.compile(r'DE LA F-?\s*(\d+)')
ZONE_IDS = list(ZONE_SCOPE.values())
ZONE_FILTER = f"IN ({', '.join(['%s'] * len(ZONE_IDS))})"


def _in_thread(fn, *args):
    try:
        return fn(*args)
    finally:
        connections.close_all()


def fetch_sales(date_from, date_to):
    """Factura and return lines in [date_from, date_to) per (doc type, month, agent, client,
    product): units, net, cost."""
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            f"""
            SELECT d.CIDDOCUMENTODE, YEAR(d.CFECHA), MONTH(d.CFECHA), d.CIDAGENTE, d.CIDCLIENTEPROVEEDOR,
                   m.CIDPRODUCTO, SUM(m.CUNIDADES), SUM({NET}), SUM(m.CCOSTOESPECIFICO)
            FROM admMovimientos m
            JOIN admDocumentos d ON d.CIDDOCUMENTO = m.CIDDOCUMENTO
            JOIN admProductos p ON p.CIDPRODUCTO = m.CIDPRODUCTO
            WHERE d.CIDDOCUMENTODE IN (%s, %s) AND d.CCANCELADO = 0 AND d.CIDAGENTE {ZONE_FILTER}
              AND d.CFECHA >= %s AND d.CFECHA < %s AND p.CCODIGOPRODUCTO <> %s
            GROUP BY d.CIDDOCUMENTODE, YEAR(d.CFECHA), MONTH(d.CFECHA), d.CIDAGENTE, d.CIDCLIENTEPROVEEDOR,
                     m.CIDPRODUCTO
            """,
            [FACTURA_DOC_TYPE, DEVOLUCION_DOC_TYPE, *ZONE_IDS, date_from, date_to, ADVANCE_PRODUCT_CODE],
        )
        return [list(r) for r in cursor.fetchall()]


def fetch_credit_notes(date_from, date_to):
    """Credit notes in the period with each application to a Factura: (note id, year, month,
    agent, client, net before IVA, total with IVA, invoice id or None, applied with IVA); the
    lines of those invoices: (invoice id, agent, client, product, net); and the ids of the notes
    that apply an advance (see is_advance_application)."""
    notes_sql = f"""
        FROM admDocumentos n
        LEFT JOIN admAsocCargosAbonos a ON a.CIDDOCUMENTOABONO = n.CIDDOCUMENTO
            AND EXISTS (SELECT 1 FROM admDocumentos ca
                        WHERE ca.CIDDOCUMENTO = a.CIDDOCUMENTOCARGO AND ca.CIDDOCUMENTODE = %s)
        WHERE n.CIDDOCUMENTODE = %s AND n.CCANCELADO = 0 AND n.CIDAGENTE {ZONE_FILTER}
          AND n.CFECHA >= %s AND n.CFECHA < %s
    """
    params = [FACTURA_DOC_TYPE, NOTA_CREDITO_DOC_TYPE, *ZONE_IDS, date_from, date_to]
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            f"""SELECT n.CIDDOCUMENTO, YEAR(n.CFECHA), MONTH(n.CFECHA), n.CIDAGENTE, n.CIDCLIENTEPROVEEDOR,
                       (n.CTOTAL - n.CIMPUESTO1) * {NOTE_RATE}, n.CTOTAL * {NOTE_RATE},
                       a.CIDDOCUMENTOCARGO, a.CIMPORTEABONO * {NOTE_RATE} {notes_sql}""",
            params,
        )
        notes = [list(r) for r in cursor.fetchall()]
        cursor.execute(
            f"""
            SELECT m.CIDDOCUMENTO, d.CIDAGENTE, d.CIDCLIENTEPROVEEDOR, m.CIDPRODUCTO, {NET}
            FROM admMovimientos m
            JOIN admDocumentos d ON d.CIDDOCUMENTO = m.CIDDOCUMENTO
            WHERE m.CIDDOCUMENTO IN (SELECT a.CIDDOCUMENTOCARGO {notes_sql})
            """,
            params,
        )
        invoice_lines = [list(r) for r in cursor.fetchall()]
        cursor.execute(
            f"""SELECT DISTINCT n.CIDDOCUMENTO,
                       CONCAT(n.CREFERENCIA, ' ', CAST(n.COBSERVACIONES AS varchar(1000))) {notes_sql}""",
            params,
        )
        texts = cursor.fetchall()
        cursor.execute(
            """
            SELECT DISTINCT d.CFOLIO FROM admMovimientos m
            JOIN admDocumentos d ON d.CIDDOCUMENTO = m.CIDDOCUMENTO
            JOIN admProductos p ON p.CIDPRODUCTO = m.CIDPRODUCTO
            WHERE d.CIDDOCUMENTODE = %s AND p.CCODIGOPRODUCTO = %s
            """,
            [FACTURA_DOC_TYPE, ADVANCE_PRODUCT_CODE],
        )
        advance_folios = {int(f) for (f,) in cursor.fetchall()}
        advances = [note_id for note_id, text in texts if is_advance_application(text, advance_folios)]
        return notes, invoice_lines, advances


def is_advance_application(text, advance_folios):
    """A credit note applies an advance when its text says ANTICIPO or names an advance invoice's
    folio ("DE LA F-17367 APLICA F-18153"). Every 2024-2025 advance had one; none without text
    since 2024-12."""
    text = (text or '').upper()
    return 'ANTICIPO' in text or any(int(f) in advance_folios for f in ADVANCE_FOLIO_RE.findall(text))


def fetch_products():
    """Every product (~1.6k) with its base unit name (for kg). All of them, not just the period's:
    credit notes reach back to older invoices."""
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            """
            SELECT p.CIDPRODUCTO, p.CCODIGOPRODUCTO, p.CNOMBREPRODUCTO, p.CTIPOPRODUCTO,
                   p.CIDVALORCLASIFICACION1, p.CIDVALORCLASIFICACION2, u.CNOMBREUNIDAD
            FROM admProductos p
            LEFT JOIN admUnidadesMedidaPeso u ON u.CIDUNIDAD = p.CIDUNIDADBASE
            """
        )
        return [list(r) for r in cursor.fetchall()]


def fetch_client_names():
    with connections['erp'].cursor() as cursor:
        cursor.execute('SELECT CIDCLIENTEPROVEEDOR, CRAZONSOCIAL FROM admClientes')
        return {cid: (name or '').strip() for cid, name in cursor.fetchall()}


def fetch_erp(date_from, date_to, refresh=False):
    key = CACHE_KEY.format(date_from, date_to)
    data = None if refresh else cache.get(key)
    if data is None:
        with ThreadPoolExecutor(max_workers=5) as pool:
            sales = pool.submit(_in_thread, fetch_sales, date_from, date_to)
            credits = pool.submit(_in_thread, fetch_credit_notes, date_from, date_to)
            products = pool.submit(_in_thread, fetch_products)
            clients = pool.submit(_in_thread, fetch_client_names)
            brands = pool.submit(_in_thread, CommissionRepository.fetch_brand_names)
            notes, invoice_lines, advances = credits.result()
            advances = set(advances)
            data = {
                'sales': sales.result(), 'notes': [n for n in notes if n[0] not in advances],
                'invoice_lines': invoice_lines,
                'products': products.result(), 'clients': clients.result(), 'brands': brands.result(),
            }
        cache.set(key, data, timeout=CACHE_SECONDS)
    return data


def allocate_credit_notes(notes, invoice_lines):
    """Spreads each credit note's net (before IVA) over the lines of the invoices it was applied
    to: first by applied amount (a note can cover several invoices), then by line net within each
    invoice. Returns rows (year, month, agent, client, product, net) - negative; whatever wasn't
    applied stays on the note's own agent and client with product None."""
    lines_by_invoice = defaultdict(list)
    for invoice_id, agent, client, product, net in invoice_lines:
        lines_by_invoice[invoice_id].append((agent, client, product, float(net)))

    by_note = defaultdict(list)
    for row in notes:
        by_note[row[0]].append(row)

    out = []
    for rows in by_note.values():
        _, year, month, agent, client, net, total = rows[0][:7]
        net, total = float(net), float(total)
        to_net = net / total if total else 0  # applications are with IVA
        left = net
        for *_, invoice_id, applied in rows:
            lines = lines_by_invoice.get(invoice_id) if invoice_id else None
            invoice_net = sum(n for *_, n in lines) if lines else 0
            if not invoice_net:
                continue
            share = float(applied) * to_net
            left -= share
            for line_agent, line_client, product, line_net in lines:
                out.append((year, month, line_agent, line_client, product, -share * line_net / invoice_net))
        if abs(left) >= 0.005:
            out.append((year, month, agent, client, None, -left))
    return out


def product_info(products, brand_names, prices, overrides, gea):
    """{product id: {code, name, brand, category, kg, source}}. kg is per sale unit; services
    weigh nothing. `prices` (net per unit sold) guard the name and GEA weights against packs."""
    info = {}
    for pid, code, name, ptype, cl1, cl2, unit in products:
        producto = {'CCODIGOPRODUCTO': code, 'CNOMBREPRODUCTO': name, 'CTIPOPRODUCTO': ptype,
                    'CIDVALORCLASIFICACION1': cl1, 'CIDVALORCLASIFICACION2': cl2}
        if pid in overrides:
            kg, source = overrides[pid], 'manual'
        elif ptype == SERVICE_PRODUCT_TYPE:
            kg, source = 0.0, 'servicio'
        else:
            kg, source = estimate_kg(code, name, prices.get(pid) or 1, gea, unit)
        brand = brand_names.get(cl1, NO_BRAND)
        info[pid] = {
            'code': code, 'name': name,
            'brand': NO_BRAND if brand in ('(Ninguna)', '') else brand,
            'category': _classify_line(producto, brand_names, set()),
            'kg': kg, 'source': source,
        }
    return info


def build_facts(sales, credit_rows, zone_of, kg_of):
    """Sums sales, returns and allocated credit notes per (month, zone, client, product).
    Rows: [month 'YYYY-MM', zone, client, product, units, net, cost, kg]."""
    facts = defaultdict(lambda: [0.0, 0.0, 0.0])
    for doc_type, year, month, agent, client, product, units, net, cost in sales:
        sign = -1 if doc_type == DEVOLUCION_DOC_TYPE else 1
        f = facts[(f'{year}-{month:02d}', zone_of(agent, client), client, product)]
        f[0] += sign * float(units)
        f[1] += sign * float(net)
        f[2] += sign * float(cost)
    for year, month, agent, client, product, net in credit_rows:
        facts[(f'{year}-{month:02d}', zone_of(agent, client), client, product)][1] += net
    return [
        [*key, round(units, 3), round(net, 2), round(cost, 2), round(units * kg_of(key[3]), 2)]
        for key, (units, net, cost) in facts.items()
    ]


def calculate_profitability(date_from, date_to, refresh=False):
    data = fetch_erp(date_from, date_to, refresh)

    units, amounts = defaultdict(float), defaultdict(float)
    for doc_type, _, _, _, _, product, u, net, _ in data['sales']:
        if doc_type == FACTURA_DOC_TYPE:
            units[product] += float(u)
            amounts[product] += float(net)
    prices = {p: amounts[p] / units[p] for p in units if units[p] > 0}
    overrides = {w.producto_id: float(w.kg) for w in ProductWeight.objects.all()}
    products = product_info(data['products'], data['brands'], prices, overrides, load_gea())

    agent_zone = {agent_id: code for code, agent_id in ZONE_SCOPE.items()}
    pv = CommissionRepository.fetch_puntoventa_clients()

    def zone_of(agent, client):
        zone = agent_zone.get(agent, PUNTOVENTA_ZONE_NAME)
        if zone == PUNTOVENTA_ZONE_NAME and client in pv:
            return pv[client].zone
        return zone

    def kg_of(product):
        return products[product]['kg'] if product in products else 0.0

    excluded = set(ExcludedProduct.objects.values_list('producto_id', flat=True))
    facts = build_facts(data['sales'], allocate_credit_notes(data['notes'], data['invoice_lines']), zone_of, kg_of)
    facts = [f for f in facts if f[3] not in excluded]
    used_products, used_clients = {f[3] for f in facts} | excluded, {f[2] for f in facts}
    return {
        'facts': facts,
        'excluded': sorted(excluded),
        'products': {pid: p for pid, p in products.items() if pid in used_products},
        'clients': {cid: name for cid, name in data['clients'].items() if cid in used_clients},
    }

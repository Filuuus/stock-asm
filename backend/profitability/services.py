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
and credit notes.

Two costs come both ways so management can switch between them on the page:
- Commissions: paid (what Comisiones actually paid, in the month it was paid - decay, overrides
  and all) or full (every invoice line at its category's base rate, no decay, in the invoice's
  month - what the Bionat report v2 used).
- Supplier discounts: the ledger's 0%-VAT purchase discounts (SUPPLIER_DISCOUNT_ACCOUNT, 99.9%
  Bionat credit notes: the 3% prompt-payment discount and others) lower the cost of Bionat
  products sold in the same posting month, pro rata by cost. Management's own view leaves them
  out (they help Bionat's cash flow more than ours).

Import costs (optional on the page): freight abroad, duties, customs brokers and port charges are
operating expenses in the ledger (IMPORT_COST_ACCOUNTS) - Comercial's purchase-expense fields are 0
on every purchase, so the ERP cost is the supplier's price alone. They're added to the cost of
imported products as one rate: the period's import costs / its foreign-currency purchases (~21% for
Oct 2025-Sep 2026). What's imported comes from our own purchases (so no supplier names here): bought
in foreign currency = imported, bought only in pesos = not (a GEA part bought from GEA's Mexican arm
already carries their import costs in its price, and "DETERGENTES NACIONALES" are made here); a
product not bought since IMPORT_HISTORY_START follows its line's (classification 2) majority, or
its brand's. Agreed with the user
2026-10-10; a per-shipment match would be more exact but the ledger references aren't reliable.

Route costs (the net result) come from app config (PoolEmployee / PoolVehicle / PoolMonthlyCost)
and land in pools, each spread over what it served (see POOL_CHOICES): payroll from Contpaqi
Nóminas (earnings + employer contributions, no PTU - same rule as the Bionat report, reproduces
it to the cent), maintenance from each vehicle's ledger account, insurance as 1/12 of the yearly
premium, plus fixed monthly amounts like the warehouse rent. Fuel and maintenance come from the
accountant's workbook (VehicleMonthlyCost, imported) for every month it covers - management's
ground truth; for later months maintenance falls back to each vehicle's ledger account and fuel to
the ledger's GAS LP account for the LP truck and GPS km (fleet app, since 2026-10-02) for the rest. Punto de Venta invoices go to the route that owns the client (PuntoVentaClientZone),
as in the Bionat report. Read-only, like every ERP access in this project.

The ERP rows are cached per period; zones, categories and kg are worked out on each request,
so a weight typed in by management shows up at once.
"""
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from django.core.cache import cache
from django.db import connections

from commissions.models import CommissionCategoryRate, ZeroCommissionProduct
from commissions.services import (
    BIONAT_SUPPLIER_NAME,
    DEVOLUCION_DOC_TYPE,
    FACTURA_DOC_TYPE,
    LEDGER_DATABASE,
    NOTA_CREDITO_DOC_TYPE,
    PUNTOVENTA_RATE_CODE,
    PUNTOVENTA_ZONE_NAME,
    ZONE_SCOPE,
    CommissionRepository,
    _classify_line,
    _rate_code_for,
    calculate_commissions,
)

from fleet.models import VehicleDayKm

from .models import ExcludedProduct, ExcludedSaleLine, PoolEmployee, PoolMonthlyCost, PoolVehicle, ProductWeight, VehicleMonthlyCost
from .weights import estimate_kg, load_gea

CACHE_KEY = 'profitability_v7_{}_{}'  # bump the version when the cached shape changes
CACHE_SECONDS = 600
NO_BRAND = 'Sin marca'
SERVICE_PRODUCT_TYPE = 3
# Net in pesos: dollar documents keep their amounts in dollars.
NET = ('(m.CNETO - m.CDESCUENTO1 - m.CDESCUENTO2 - m.CDESCUENTO3 - m.CDESCUENTO4 - m.CDESCUENTO5)'
       ' * CASE WHEN d.CIDMONEDA = 1 THEN 1 ELSE d.CTIPOCAMBIO END')
NOTE_RATE = 'CASE WHEN n.CIDMONEDA = 1 THEN 1 ELSE n.CTIPOCAMBIO END'
ADVANCE_PRODUCT_CODE = '84111506'  # SAT key "anticipo"; ERP name "ANTICIPO APLICABLE A FACTURA"
# "APLICACION DE ANTICIPO DE LA F-19411 A LA F-19456", or without the word: "DE LA F-17367 APLICA F-18153".
SUPPLIER_DISCOUNT_ACCOUNT = '500200001'  # DESCUENTOS SOBRE COMPRAS TASA 0%
# Freight abroad, IGI, DTA, PRV, "costo indirecto" (ports, brokers), tariff, customs brokers' fees.
IMPORT_COST_ACCOUNTS = ('500503017', '500508001', '500508002', '500508003', '500508005', '500506010', '500502005')
PURCHASE_DOC_TYPE = 19
IMPORT_HISTORY_START = date(2024, 1, 1)  # how far back purchases are read to tell what's imported
LP_FUEL_ACCOUNT = '500503021'  # GAS LP (selling expenses); only the Zona 1 truck burns LP since the F-350 retired
MAINTENANCE_ACCOUNTS = '5_0511%'  # one account per vehicle
PAYROLL_DATABASE = 'ctNOMAGROPECUARIA'  # Contpaqi Nóminas
PTU_CONCEPT_NUMBER = 25  # "Reparto de utilidades": varies by year, unrelated to the routes (management)
ADVANCE_FOLIO_RE = re.compile(r'DE LA F-?\s*(\d+)')
ZONE_IDS = list(ZONE_SCOPE.values())
ZONE_FILTER = f"IN ({', '.join(['%s'] * len(ZONE_IDS))})"


def _in_thread(fn, *args):
    try:
        return fn(*args)
    finally:
        connections.close_all()


def fetch_sales(date_from, date_to):
    """Factura and return lines in [date_from, date_to), one row per line (the cost is corrected
    line by line, see correct_dollar_cost): line id, doc type, date, agent, client, product,
    product type, units, net, cost."""
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            f"""
            SELECT m.CIDMOVIMIENTO, d.CIDDOCUMENTODE, d.CFECHA, d.CIDAGENTE, d.CIDCLIENTEPROVEEDOR, m.CIDPRODUCTO,
                   p.CTIPOPRODUCTO, m.CUNIDADES, {NET}, m.CCOSTOESPECIFICO
            FROM admMovimientos m
            JOIN admDocumentos d ON d.CIDDOCUMENTO = m.CIDDOCUMENTO
            JOIN admProductos p ON p.CIDPRODUCTO = m.CIDPRODUCTO
            WHERE d.CIDDOCUMENTODE IN (%s, %s) AND d.CCANCELADO = 0 AND d.CIDAGENTE {ZONE_FILTER}
              AND d.CFECHA >= %s AND d.CFECHA < %s AND p.CCODIGOPRODUCTO <> %s
            """,
            [FACTURA_DOC_TYPE, DEVOLUCION_DOC_TYPE, *ZONE_IDS, date_from, date_to, ADVANCE_PRODUCT_CODE],
        )
        return cursor.fetchall()


def fetch_dollar_purchases():
    """Every purchase line priced in dollars: {product: [(date, dollar price, exchange rate)]},
    oldest first. Dollar-priced means a foreign-currency purchase, or one entered in pesos from a
    supplier that bills us in dollars (North West Rubber's 2023-2025 purchases were entered that way,
    found 2026-10-13). Also returns every product ever purchased."""
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            """
            SELECT m.CIDPRODUCTO, d.CFECHA, m.CPRECIO, d.CTIPOCAMBIO, d.CIDMONEDA, d.CIDCLIENTEPROVEEDOR
            FROM admMovimientos m
            JOIN admDocumentos d ON d.CIDDOCUMENTO = m.CIDDOCUMENTO
            WHERE d.CIDDOCUMENTODE = %s AND d.CCANCELADO = 0 AND m.CUNIDADES > 0
            ORDER BY d.CFECHA
            """,
            [PURCHASE_DOC_TYPE],
        )
        rows = cursor.fetchall()
    dollar_suppliers = {supplier for _, _, _, _, currency, supplier in rows if currency != 1}
    dollar = defaultdict(list)
    for product, day, price, rate, currency, supplier in rows:
        if price and float(rate) > 1 and (currency != 1 or supplier in dollar_suppliers):
            dollar[product].append((day.date(), float(price), float(rate)))
    return dict(dollar), {r[0] for r in rows}


def correct_dollar_cost(units, net, cost, day, purchases):
    """A sale line's cost in pesos, fixing the ERP's dollar costs read as pesos (management,
    2026-10-13). `purchases`: the product's dollar purchases, oldest first (fetch_dollar_purchases).
    - The cost per unit is one purchase's dollar price (within 2%): times that purchase's rate.
    - The average cost was dragged down by such lots (under 30% of the latest purchase before the sale
      at its rate): that purchase's price at its rate.
    Either only when the corrected cost stays under the selling price and the recorded one is under a
    fifth of it, so a real peso cost (17-20 times higher) or a box-vs-piece unit is never touched."""
    if not purchases or units <= 0 or cost <= 0 or net <= 0:
        return cost
    per_unit, price = cost / units, net / units
    if per_unit * 5 >= price:
        return cost
    for _, dollars, rate in purchases:
        if abs(per_unit - dollars) <= 0.02 * dollars and dollars * rate < price:
            return cost * rate
    latest = next((p for p in reversed(purchases) if p[0] <= day), purchases[0])
    reference = latest[1] * latest[2]
    if per_unit < 0.3 * reference and reference < price:
        return units * reference
    return cost


def aggregate_sales(lines, dollar_purchases, purchased, excluded_lines=frozenset()):
    """Corrects each line's cost and sums lines per (doc type, year, month, agent, client, product):
    units, net, cost - the shape build_facts takes. Lines whose id is in `excluded_lines` are left out. Also returns the goods without a usable cost: a sale line at cost 0, or never
    purchased and over 80% gross margin (their cost is a guess)."""
    groups = defaultdict(lambda: [0.0, 0.0, 0.0])
    zero_cost, totals = set(), defaultdict(lambda: [0.0, 0.0])
    for line_id, doc_type, day, agent, client, product, product_type, units, net, cost in lines:
        if line_id in excluded_lines:
            continue
        units, net, cost = float(units), float(net), float(cost)
        if product_type != SERVICE_PRODUCT_TYPE:
            cost = correct_dollar_cost(units, net, cost, day.date(), dollar_purchases.get(product))
            if doc_type == FACTURA_DOC_TYPE:
                if units > 0 and cost == 0:
                    zero_cost.add(product)
                totals[product][0] += net
                totals[product][1] += cost
        g = groups[(doc_type, day.year, day.month, agent, client, product)]
        g[0] += units
        g[1] += net
        g[2] += cost
    guessed = {p for p, (net, cost) in totals.items() if p not in purchased and net > 0 and (net - cost) / net > 0.8}
    rows = [[*key, *values] for key, values in groups.items()]
    return rows, sorted(zero_cost | guessed)


def fetch_credit_notes(date_from, date_to):
    """Credit notes in the period with each application to a Factura: (note id, year, month,
    agent, client, net before IVA, total with IVA, invoice id or None, applied with IVA); the
    lines of those invoices: (line id, invoice id, agent, client, product, net); and the ids of the notes
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
            SELECT m.CIDMOVIMIENTO, m.CIDDOCUMENTO, d.CIDAGENTE, d.CIDCLIENTEPROVEEDOR, m.CIDPRODUCTO, {NET}
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


def fetch_paid_commissions(date_from, date_to):
    """Commissions paid in the period, as Comisiones computes them: (month paid, zone, client,
    product code, amount). Manual flat corrections carry no product."""
    result = calculate_commissions(date_from, date_to - timedelta(days=1))
    return [
        (f"{line['paid_date']:%Y-%m}" if line.get('paid_date') else f'{date_from:%Y-%m}', line['zone'],
         line['client_id'], line.get('producto_codigo'), float(line['commission']))
        for line in result['lines']
    ]


def fetch_supplier_discounts(date_from, date_to):
    """{'YYYY-MM': amount} credited to SUPPLIER_DISCOUNT_ACCOUNT per posting month (1-12; 13/14 are
    year-end adjustments)."""
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            f"""
            SELECT m.Ejercicio, m.Periodo, SUM(CASE WHEN m.TipoMovto = 1 THEN m.Importe ELSE -m.Importe END)
            FROM {LEDGER_DATABASE}.dbo.MovimientosPoliza m
            JOIN {LEDGER_DATABASE}.dbo.Cuentas cu ON cu.Id = m.IdCuenta
            WHERE cu.Codigo = %s AND m.Periodo BETWEEN 1 AND 12
              AND m.Ejercicio * 100 + m.Periodo >= %s AND m.Ejercicio * 100 + m.Periodo < %s
            GROUP BY m.Ejercicio, m.Periodo
            """,
            [SUPPLIER_DISCOUNT_ACCOUNT, date_from.year * 100 + date_from.month, date_to.year * 100 + date_to.month],
        )
        return {f'{y}-{m:02d}': float(amount) for y, m, amount in cursor.fetchall()}


def _month_key(date_from, date_to):
    return [date_from.year * 100 + date_from.month, date_to.year * 100 + date_to.month]


def fetch_payroll(date_from, date_to):
    """{('YYYY-MM', employee id): earnings + employer contributions}, by each closed (afectado)
    period's month, without PTU."""
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            f"""
            SELECT p.ejercicio, p.mes, m.idempleado, SUM(m.importetotal)
            FROM {PAYROLL_DATABASE}.dbo.nom10007 m
            JOIN {PAYROLL_DATABASE}.dbo.nom10002 p ON p.idperiodo = m.idperiodo
            JOIN {PAYROLL_DATABASE}.dbo.nom10004 c ON c.idconcepto = m.idconcepto
            WHERE p.afectado = 1 AND c.tipoconcepto IN ('P', 'O') AND c.numeroconcepto <> %s
              AND p.ejercicio * 100 + p.mes >= %s AND p.ejercicio * 100 + p.mes < %s
            GROUP BY p.ejercicio, p.mes, m.idempleado
            """,
            [PTU_CONCEPT_NUMBER, *_month_key(date_from, date_to)],
        )
        return {(f'{y}-{m:02d}', employee): float(amount) for y, m, employee, amount in cursor.fetchall()}


def fetch_vehicle_ledger(date_from, date_to):
    """{('YYYY-MM', account code): net debit} for the vehicle maintenance accounts and GAS LP."""
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            f"""
            SELECT m.Ejercicio, m.Periodo, cu.Codigo, SUM(CASE WHEN m.TipoMovto = 0 THEN m.Importe ELSE -m.Importe END)
            FROM {LEDGER_DATABASE}.dbo.MovimientosPoliza m
            JOIN {LEDGER_DATABASE}.dbo.Cuentas cu ON cu.Id = m.IdCuenta
            WHERE (cu.Codigo LIKE %s OR cu.Codigo = %s) AND m.Periodo BETWEEN 1 AND 12
              AND m.Ejercicio * 100 + m.Periodo >= %s AND m.Ejercicio * 100 + m.Periodo < %s
            GROUP BY m.Ejercicio, m.Periodo, cu.Codigo
            """,
            [MAINTENANCE_ACCOUNTS, LP_FUEL_ACCOUNT, *_month_key(date_from, date_to)],
        )
        return {(f'{y}-{m:02d}', code): float(amount) for y, m, code, amount in cursor.fetchall()}


def fetch_imports(date_from, date_to):
    """{'cost': import costs posted in the period, 'purchases': foreign-currency purchases in the
    period (pesos, before IVA), plus what our purchases say about where products come from (see
    imported_products)}."""
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            f"""
            SELECT SUM(CASE WHEN m.TipoMovto = 0 THEN m.Importe ELSE -m.Importe END)
            FROM {LEDGER_DATABASE}.dbo.MovimientosPoliza m
            JOIN {LEDGER_DATABASE}.dbo.Cuentas cu ON cu.Id = m.IdCuenta
            WHERE cu.Codigo IN ({', '.join(['%s'] * len(IMPORT_COST_ACCOUNTS))}) AND m.Periodo BETWEEN 1 AND 12
              AND m.Ejercicio * 100 + m.Periodo >= %s AND m.Ejercicio * 100 + m.Periodo < %s
            """,
            [*IMPORT_COST_ACCOUNTS, *_month_key(date_from, date_to)],
        )
        cost = float(cursor.fetchone()[0] or 0)
        cursor.execute(
            """
            SELECT SUM((d.CTOTAL - d.CIMPUESTO1) * d.CTIPOCAMBIO) FROM admDocumentos d
            WHERE d.CIDDOCUMENTODE = %s AND d.CCANCELADO = 0 AND d.CIDMONEDA <> 1 AND d.CFECHA >= %s AND d.CFECHA < %s
            """,
            [PURCHASE_DOC_TYPE, date_from, date_to],
        )
        purchases = float(cursor.fetchone()[0] or 0)
        # Purchases per product since IMPORT_HISTORY_START: (product, line, brand, foreign, total) in pesos.
        cursor.execute(
            """
            SELECT p.CIDPRODUCTO, p.CIDVALORCLASIFICACION2, p.CIDVALORCLASIFICACION1,
                   SUM(CASE WHEN d.CIDMONEDA <> 1 THEN m.CNETO * d.CTIPOCAMBIO ELSE 0 END),
                   SUM(m.CNETO * CASE WHEN d.CIDMONEDA = 1 THEN 1 ELSE d.CTIPOCAMBIO END)
            FROM admMovimientos m
            JOIN admDocumentos d ON d.CIDDOCUMENTO = m.CIDDOCUMENTO
            JOIN admProductos p ON p.CIDPRODUCTO = m.CIDPRODUCTO
            WHERE d.CIDDOCUMENTODE = %s AND d.CCANCELADO = 0 AND d.CFECHA >= %s
            GROUP BY p.CIDPRODUCTO, p.CIDVALORCLASIFICACION2, p.CIDVALORCLASIFICACION1
            """,
            [PURCHASE_DOC_TYPE, IMPORT_HISTORY_START],
        )
        rows = [list(r) for r in cursor.fetchall()]
    return {'cost': cost, 'purchases': purchases, 'purchase_rows': rows}


def imported_products(purchase_rows, catalog):
    """Ids of the imported products in `catalog` ((product, line, brand) for every product).
    `purchase_rows`: (product, line, brand, foreign amount, total amount) - our purchases. A product
    we bought is imported if any of it came in foreign currency; one we didn't buy follows the
    majority (by value) of its line, or of its brand when its line has no purchases."""
    bought, foreign_line, total_line, foreign_brand, total_brand = {}, *(defaultdict(float) for _ in range(4))
    for product, line, brand, foreign_amount, total_amount in purchase_rows:
        foreign_amount, total_amount = float(foreign_amount or 0), float(total_amount or 0)
        bought[product] = bought.get(product, False) or foreign_amount > 0
        if line:
            foreign_line[line] += foreign_amount
            total_line[line] += total_amount
        if brand:
            foreign_brand[brand] += foreign_amount
            total_brand[brand] += total_amount

    def mostly_foreign(key, foreign, total):
        return bool(key) and total.get(key, 0) > 0 and foreign[key] / total[key] > 0.5

    out = set()
    for product, line, brand in catalog:
        if product in bought:
            is_imported = bought[product]
        elif line and total_line.get(line, 0) > 0:
            is_imported = mostly_foreign(line, foreign_line, total_line)
        else:
            is_imported = mostly_foreign(brand, foreign_brand, total_brand)
        if is_imported:
            out.add(product)
    return out


def fetch_erp(date_from, date_to, refresh=False):
    key = CACHE_KEY.format(date_from, date_to)
    data = None if refresh else cache.get(key)
    if data is None:
        with ThreadPoolExecutor(max_workers=10) as pool:
            imports = pool.submit(_in_thread, fetch_imports, date_from, date_to)
            payroll = pool.submit(_in_thread, fetch_payroll, date_from, date_to)
            vehicle_ledger = pool.submit(_in_thread, fetch_vehicle_ledger, date_from, date_to)
            commissions = pool.submit(_in_thread, fetch_paid_commissions, date_from, date_to)
            discounts = pool.submit(_in_thread, fetch_supplier_discounts, date_from, date_to)
            sales = pool.submit(_in_thread, fetch_sales, date_from, date_to)
            dollar = pool.submit(_in_thread, fetch_dollar_purchases)
            credits = pool.submit(_in_thread, fetch_credit_notes, date_from, date_to)
            products = pool.submit(_in_thread, fetch_products)
            clients = pool.submit(_in_thread, fetch_client_names)
            brands = pool.submit(_in_thread, CommissionRepository.fetch_brand_names)
            notes, invoice_lines, advances = credits.result()
            advances = set(advances)
            dollar_purchases, purchased = dollar.result()
            data = {
                # Raw lines: aggregated per request, after the invoice-line exclusions (see calculate_profitability).
                'sale_lines': sales.result(), 'dollar_purchases': dollar_purchases, 'purchased': purchased,
                'notes': [n for n in notes if n[0] not in advances],
                'invoice_lines': invoice_lines,
                'products': products.result(), 'clients': clients.result(), 'brands': brands.result(),
                'commissions': commissions.result(), 'supplier_discounts': discounts.result(),
                'payroll': payroll.result(), 'vehicle_ledger': vehicle_ledger.result(), 'imports': imports.result(),
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


def build_facts(sales, credit_rows, commission_rows, zone_of, kg_of, rate_of):
    """Sums sales, returns, allocated credit notes and paid commissions per (month, zone, client,
    product). Rows: [month 'YYYY-MM', zone, client, product, units, net, cost, kg, full commission,
    paid commission, supplier discount, route cost by kg, route cost by piece, import cost (the last
    four 0 here, see allocate_supplier_discounts, allocate_route_costs and calculate_profitability)]."""
    facts = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0.0])
    for doc_type, year, month, agent, client, product, units, net, cost in sales:
        sign = -1 if doc_type == DEVOLUCION_DOC_TYPE else 1
        zone = zone_of(agent, client)
        f = facts[(f'{year}-{month:02d}', zone, client, product)]
        f[0] += sign * float(units)
        f[1] += sign * float(net)
        f[2] += sign * float(cost)
        f[3] += sign * float(net) * rate_of(zone, client, product)
    for year, month, agent, client, product, net in credit_rows:
        facts[(f'{year}-{month:02d}', zone_of(agent, client), client, product)][1] += net
    for month, zone, client, product, amount in commission_rows:
        facts[(month, zone, client, product)][4] += amount
    return [
        [*key, round(units, 3), round(net, 2), round(cost, 2), round(units * kg_of(key[3]), 2),
         round(full, 2), round(paid, 2), 0.0, 0.0, 0.0, 0.0]
        for key, (units, net, cost, full, paid) in facts.items()
    ]


def allocate_supplier_discounts(facts, discounts, applies_to):
    """Writes each month's supplier discount into column 10 of the facts whose product it applies
    to, pro rata by their cost that month."""
    # ponytail: by sales cost of the posting month, not the purchases the discount came from; fine
    # for a monthly-bought line like Bionat, a FIFO match if it ever matters.
    cost = defaultdict(float)
    for f in facts:
        if applies_to(f[3]):
            cost[f[0]] += f[6]
    for f in facts:
        if applies_to(f[3]) and cost[f[0]] > 0:
            f[10] = round(discounts.get(f[0], 0.0) * f[6] / cost[f[0]], 2)
    return facts


def route_costs(months, employees, vehicles, monthly_costs, payroll, ledger, km, workbook):
    """{month: {pool: {component: amount}}}. `employees` {id: pool}; `vehicles` dicts with pool,
    sheet_name, maintenance_account, uses_lp, gps_imei, km_per_liter, price_per_liter,
    annual_insurance; `monthly_costs` [(pool, label, amount)]; `km` {(month, imei): km};
    `workbook` {(month, sheet name, 'fuel' | 'maintenance'): amount} - a month with any fuel entry
    there takes both from it, for every vehicle it names."""
    covered = {m for m, _, kind in workbook if kind == 'fuel'}
    out = {m: defaultdict(lambda: defaultdict(float)) for m in months}
    for m in months:
        for employee, pool in employees.items():
            out[m][pool]['Sueldos'] += payroll.get((m, employee), 0.0)
        for v in vehicles:
            costs = out[m][v['pool']]
            costs['Seguros'] += v['annual_insurance'] / 12
            if m in covered and v['sheet_name']:
                costs['Combustible'] += workbook.get((m, v['sheet_name'], 'fuel'), 0.0)
                costs['Mantenimiento'] += workbook.get((m, v['sheet_name'], 'maintenance'), 0.0)
                continue
            if v['maintenance_account']:
                costs['Mantenimiento'] += ledger.get((m, v['maintenance_account']), 0.0)
            if v['uses_lp']:
                costs['Combustible'] += ledger.get((m, LP_FUEL_ACCOUNT), 0.0)
            elif v['gps_imei'] and v['km_per_liter'] and v['price_per_liter']:
                costs['Combustible'] += km.get((m, v['gps_imei']), 0.0) / v['km_per_liter'] * v['price_per_liter']
        for pool, label, amount in monthly_costs:
            out[m][pool][label] += amount
    return {m: {pool: {k: round(v, 2) for k, v in c.items() if v} for pool, c in pools.items() if any(c.values())}
            for m, pools in out.items()}


def allocate_route_costs(facts, costs, is_service, by='kg'):
    """Writes each fact's share of the month's pools into column 11 (by='kg') or 12 (by='pieces'):
    a route's pool over its own zone's kg or pieces, the warehouse over every kg or piece, the
    service crew over service sales. Pieces are units sold of anything but services (Bionat report
    v1). Returns {month: {pool: amount}} that found nothing to land on."""
    column = 11 if by == 'kg' else 12

    def goods(f):
        if by == 'kg':
            return f[7]
        return f[4] if f[3] is not None and not is_service(f[3]) else 0.0

    def weight(f, pool):
        if pool == 'SERVICIOS':
            return f[5] if is_service(f[3]) else 0.0
        return goods(f) if pool == 'ALMACEN' or f[1] == pool else 0.0

    by_month = defaultdict(list)
    for f in facts:
        by_month[f[0]].append(f)
    unallocated = defaultdict(dict)
    for month, pools in costs.items():
        rows = by_month.get(month, [])
        for pool, components in pools.items():
            amount = sum(components.values())
            total = sum(weight(f, pool) for f in rows)
            if total <= 0:
                unallocated[month][pool] = round(amount, 2)
                continue
            for f in rows:
                w = weight(f, pool)
                if w:
                    f[column] = round(f[column] + amount * w / total, 2)
    return dict(unallocated)


def calculate_profitability(date_from, date_to, refresh=False, drop=frozenset()):
    """`drop`: product ids to imagine not selling (the page's what-if checkboxes). Their sales, cost,
    commissions and supplier discounts go; the route costs stay - salaries, trucks and rent don't
    leave with a product - and are spread over what's left."""
    data = fetch_erp(date_from, date_to, refresh)
    line_exclusions = list(ExcludedSaleLine.objects.filter(date__gte=date_from, date__lt=date_to))
    excluded_lines = {e.movement_id for e in line_exclusions}
    sales, unreliable_cost = aggregate_sales(data['sale_lines'], data['dollar_purchases'], data['purchased'],
                                             excluded_lines)
    invoice_lines = [line[1:] for line in data['invoice_lines'] if line[0] not in excluded_lines]

    units, amounts = defaultdict(float), defaultdict(float)
    for doc_type, _, _, _, _, product, u, net, _ in sales:
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

    base_rates = {r.code: float(r.base_rate) for r in CommissionCategoryRate.objects.filter(active=True)}
    zero_codes = set(ZeroCommissionProduct.objects.filter(active=True).values_list('producto_codigo', flat=True))

    def rate_of(zone, client, product):
        """Base commission rate of a line, with Comisiones' own rules (Punto de Venta flat rate,
        zero-commission products, services by who sold them)."""
        p = products.get(product)
        if not p or p['code'] in zero_codes:
            return 0.0
        if client in pv and pv[client].applies_to(p['code']):
            return base_rates.get(PUNTOVENTA_RATE_CODE, 0.0)
        return base_rates.get(_rate_code_for(p['category'], zone), 0.0)

    product_id = {p['code']: pid for pid, p in products.items()}
    commission_rows = [(m, zone, client, product_id.get(code), amount)
                       for m, zone, client, code, amount in data['commissions']]

    excluded = set(ExcludedProduct.objects.values_list('producto_id', flat=True))
    facts = build_facts(sales, allocate_credit_notes(data['notes'], invoice_lines),
                        commission_rows, zone_of, kg_of, rate_of)
    facts = [f for f in facts if f[3] not in excluded and f[3] not in drop]
    imports = data['imports']
    import_rate = imports['cost'] / imports['purchases'] if imports['purchases'] else 0.0
    imported_ids = imported_products(imports['purchase_rows'],
                                     [(pid, line, brand) for pid, _, _, _, brand, line, _ in data['products']])
    for f in facts:
        if f[3] in imported_ids:
            f[13] = round(f[6] * import_rate, 2)
    allocate_supplier_discounts(facts, data['supplier_discounts'],
                                lambda pid: pid in products and products[pid]['brand'] == BIONAT_SUPPLIER_NAME)

    months = []
    d = date_from
    while d < date_to:
        months.append(f'{d:%Y-%m}')
        d = date(d.year + d.month // 12, d.month % 12 + 1, 1)
    vehicles = [{
        'pool': v.pool, 'sheet_name': v.sheet_name, 'maintenance_account': v.maintenance_account, 'uses_lp': v.uses_lp,
        'gps_imei': v.gps_imei, 'km_per_liter': float(v.km_per_liter or 0),
        'price_per_liter': float(v.price_per_liter or 0), 'annual_insurance': float(v.annual_insurance),
    } for v in PoolVehicle.objects.all()]
    km = defaultdict(float)
    for imei, day, value in VehicleDayKm.objects.filter(day__gte=date_from, day__lt=date_to).values_list(
            'imei', 'day', 'km'):
        km[(f'{day:%Y-%m}', imei)] += float(value)
    costs = route_costs(
        months, dict(PoolEmployee.objects.values_list('employee_id', 'pool')), vehicles,
        [(c.pool, c.label, float(c.monthly_amount)) for c in PoolMonthlyCost.objects.all()],
        data['payroll'], data['vehicle_ledger'], km,
        {(c.month, c.vehicle, c.kind): float(c.amount)
         for c in VehicleMonthlyCost.objects.filter(month__gte=months[0], month__lte=months[-1])},
    )
    is_service = lambda pid: pid in products and products[pid]['category'] == 'S'  # noqa: E731
    unallocated = allocate_route_costs(facts, costs, is_service)
    allocate_route_costs(facts, costs, is_service, by='pieces')
    first_gps = VehicleDayKm.objects.order_by('day').values_list('day', flat=True).first()
    used_products = {f[3] for f in facts} | excluded | set(drop) | {e.producto_id for e in line_exclusions}
    used_clients = {f[2] for f in facts} | {e.client_id for e in line_exclusions}
    return {
        'facts': facts,
        'excluded': sorted(excluded),
        'unreliable_cost': [p for p in unreliable_cost if p not in excluded],
        'excluded_lines': [{'line_id': e.movement_id, 'document_id': e.document_id, 'product_id': e.producto_id,
                            'folio': e.folio,
                            'date': e.date.isoformat(), 'client_id': e.client_id, 'reason': e.reason}
                           for e in sorted(line_exclusions, key=lambda e: (e.date, e.folio))],
        'dropped': sorted(drop),
        'imports': {'cost': round(imports['cost'], 2), 'purchases': round(imports['purchases'], 2),
                    'rate': round(import_rate, 4)},
        'route_costs': costs,
        'unallocated': unallocated,
        'gps_since': first_gps.isoformat() if first_gps else None,
        'workbook_through': VehicleMonthlyCost.objects.order_by('-month').values_list('month', flat=True).first(),
        'products': {pid: p for pid, p in products.items() if pid in used_products},
        'clients': {cid: name for cid, name in data['clients'].items() if cid in used_clients},
    }


def product_invoices(date_from, date_to, product_id, client_id=None, zone=None):
    """The invoice and return lines behind a product's figures in the period (same rules as the
    facts: scoped zones, not cancelled, pesos), optionally for one client and/or zone. Credit notes
    spread over the product aren't listed - they're shown on the invoice itself."""
    params = [FACTURA_DOC_TYPE, DEVOLUCION_DOC_TYPE, *ZONE_IDS, date_from, date_to, product_id]
    client_sql = ''
    if client_id is not None:
        client_sql = 'AND d.CIDCLIENTEPROVEEDOR = %s'
        params.append(client_id)
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            f"""
            SELECT d.CIDDOCUMENTO, d.CIDDOCUMENTODE, d.CIDCONCEPTODOCUMENTO, d.CFOLIO, d.CFECHA, d.CIDAGENTE,
                   d.CIDCLIENTEPROVEEDOR, m.CUNIDADES, {NET}, m.CCOSTOESPECIFICO, p.CTIPOPRODUCTO, m.CIDMOVIMIENTO
            FROM admMovimientos m
            JOIN admDocumentos d ON d.CIDDOCUMENTO = m.CIDDOCUMENTO
            JOIN admProductos p ON p.CIDPRODUCTO = m.CIDPRODUCTO
            WHERE d.CIDDOCUMENTODE IN (%s, %s) AND d.CCANCELADO = 0 AND d.CIDAGENTE {ZONE_FILTER}
              AND d.CFECHA >= %s AND d.CFECHA < %s AND m.CIDPRODUCTO = %s {client_sql}
            ORDER BY d.CFECHA DESC, d.CFOLIO DESC
            """,
            params,
        )
        lines = cursor.fetchall()
    # Same cost correction as the facts; one row per line, so a gift next to a paid line can be left out alone.
    purchases = fetch_dollar_purchases()[0].get(product_id)
    excluded = set(ExcludedSaleLine.objects.filter(producto_id=product_id).values_list('movement_id', flat=True))
    rows = []
    for doc_id, doc_type, concept, folio, day, agent, client, units, net, cost, product_type, line_id in lines:
        units, net, cost = float(units), float(net), float(cost)
        if product_type != SERVICE_PRODUCT_TYPE:
            cost = correct_dollar_cost(units, net, cost, day.date(), purchases)
        rows.append([doc_id, doc_type, concept, folio, day, agent, client, units, net, cost, line_id])
    series = CommissionRepository.fetch_concepto_series()
    clients = fetch_client_names()
    agent_zone = {agent_id: code for code, agent_id in ZONE_SCOPE.items()}
    pv = CommissionRepository.fetch_puntoventa_clients()
    out = []
    for doc_id, doc_type, concept, folio, day, agent, client, units, net, cost, line_id in rows:
        line_zone = agent_zone.get(agent, PUNTOVENTA_ZONE_NAME)
        if line_zone == PUNTOVENTA_ZONE_NAME and client in pv:
            line_zone = pv[client].zone
        if zone and line_zone != zone:
            continue
        sign = -1 if doc_type == DEVOLUCION_DOC_TYPE else 1
        out.append({
            'invoice_id': doc_id,
            'folio': f"{series.get(concept, 'F')} {int(folio)}",
            'return': doc_type == DEVOLUCION_DOC_TYPE,
            'date': day.date().isoformat(),
            'zone': line_zone,
            'client_id': client,
            'client': clients.get(client, ''),
            'units': sign * float(units),
            'net': round(sign * float(net), 2),
            'cost': round(sign * float(cost), 2),
            'line_id': line_id,
            'excluded': line_id in excluded,
        })
    return out

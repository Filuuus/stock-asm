"""Sales BI for management: monthly sales, gross margin, zone and brand mix.

What counts as a sale is the commissions / Corte de Caja rule: Facturas
(CIDDOCUMENTODE 4), not cancelled, in the ZONE_SCOPE zones. Returns (5) and
credit notes (7) net against sales in the month they were issued. Amounts are
before IVA: line CNETO minus discounts, which equals the header CTOTAL minus
CIMPUESTO1 (checked on Aug 2026). Cost is the ERP's CCOSTOESPECIFICO per line;
services carry no cost. Read-only, like every ERP access in this project.
"""
import re
from collections import defaultdict
from datetime import date, timedelta

from django.db import connections

from commissions.services import (
    DEVOLUCION_DOC_TYPE,
    FACTURA_DOC_TYPE,
    NOTA_CREDITO_DOC_TYPE,
    ZONE_SCOPE,
    LEDGER_DATABASE,
    CommissionRepository,
)
from corte_de_caja.services import calculate_corte_de_caja

NO_BRAND = 'Sin marca'

# Contabilidad results accounts, by the first 4 digits of Cuentas.Codigo.
LEDGER_INCOME_GROUPS = ('4001', '4002')  # sales, minus discounts/returns
LEDGER_COST_GROUPS = ('5001', '5002')  # cost of sales, minus purchase discounts
LEDGER_EXPENSE_GROUPS = ('5003', '5005', '5006')  # depreciation, selling, administration
LEDGER_FINANCIAL_GROUPS = ('4003', '4004', '5007', '5008')  # other/financial income and expenses
# Expense categories, matched on whole words of the account name (so "IGI"
# doesn't match "VIGILANCIA"). First match wins; anything else is "Otros".
# ponytail: name keywords, agreed with the user 2026-10-02 - pending the
# accountant's review; a new account with an unexpected name lands in Otros.
EXPENSE_CATEGORIES = [
    ('Nómina', re.compile(
        r'\b(SUELDOS|SALARIOS|IMSS|INFONAVIT|RETIRO|PREMIOS|VACACIONES|VACACIONAL|AGUINALDO|NOMINAS|DESPENSA|PTU)\b')),
    ('Fletes e importación', re.compile(r'\b(FLETES|ACARREOS|IGI|ARANCELARIA|ADUANALES|DTA|PRV)\b')),
    ('Combustible', re.compile(r'\b(COMBUSTIBLES|GAS LP|GASOLINA|DIESEL)\b')),
    ('Seguros', re.compile(r'\bSEGUROS Y FIANZAS\b')),
]
OTHER_EXPENSES = 'Otros'


def fetch_month_lines(date_from, date_to):
    """Sales, returns and credit-note lines in [date_from, date_to), summed per
    (year, month, document type, zone id, brand id): net before IVA and cost."""
    zone_ids = list(ZONE_SCOPE.values())
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            f"""
            SELECT YEAR(d.CFECHA), MONTH(d.CFECHA), d.CIDDOCUMENTODE, d.CIDAGENTE, p.CIDVALORCLASIFICACION1,
                   SUM(m.CNETO - m.CDESCUENTO1 - m.CDESCUENTO2 - m.CDESCUENTO3 - m.CDESCUENTO4 - m.CDESCUENTO5),
                   SUM(m.CCOSTOESPECIFICO)
            FROM admMovimientos m
            JOIN admDocumentos d ON d.CIDDOCUMENTO = m.CIDDOCUMENTO
            LEFT JOIN admProductos p ON p.CIDPRODUCTO = m.CIDPRODUCTO
            WHERE d.CIDDOCUMENTODE IN (%s, %s, %s) AND d.CCANCELADO = 0
              AND d.CIDAGENTE IN ({', '.join(['%s'] * len(zone_ids))})
              AND d.CFECHA >= %s AND d.CFECHA < %s
            GROUP BY YEAR(d.CFECHA), MONTH(d.CFECHA), d.CIDDOCUMENTODE, d.CIDAGENTE, p.CIDVALORCLASIFICACION1
            """,
            [FACTURA_DOC_TYPE, DEVOLUCION_DOC_TYPE, NOTA_CREDITO_DOC_TYPE, *zone_ids, date_from, date_to],
        )
        return cursor.fetchall()


def summarize(rows, year, month, brand_names):
    """Pure part of calculate_sales: rows from fetch_month_lines covering
    January of year-1 through (year, month)."""
    zone_by_id = {v: k for k, v in ZONE_SCOPE.items()}
    keys = [f'{y}-{m:02d}' for y in (year - 1, year) for m in range(1, 13) if (y, m) <= (year, month)]
    months = {k: {'month': k, 'ventas': 0.0, 'devoluciones': 0.0, 'costo': 0.0,
                  'zonas': {z: 0.0 for z in ZONE_SCOPE}} for k in keys}
    brands = defaultdict(lambda: {'ytd': 0.0, 'ytd_prev': 0.0})

    for y, m, doc_type, zone_id, brand_id, net, cost in rows:
        row = months[f'{y}-{m:02d}']
        sign = 1 if doc_type == FACTURA_DOC_TYPE else -1
        net, cost = sign * (net or 0), sign * (cost or 0)
        row['ventas'] += net
        row['costo'] += cost
        row['zonas'][zone_by_id[zone_id]] += net
        if sign < 0:
            row['devoluciones'] -= net
        if m <= month:
            brands[brand_names.get(brand_id, NO_BRAND).replace('(Ninguna)', NO_BRAND)]['ytd' if y == year else 'ytd_prev'] += net

    def rounded(d):
        return {k: rounded(v) if isinstance(v, dict) else round(v, 2) if isinstance(v, float) else v for k, v in d.items()}

    return {
        'months': [rounded(months[k]) for k in keys],
        'brands': sorted(({'brand': b, **rounded(v)} for b, v in brands.items()), key=lambda b: -b['ytd']),
    }


def fetch_ledger_results(date_from, date_to):
    """Contabilidad results accounts, net debit (cargos minus abonos) per
    (year, period, 4-digit group, account name). Periods 13+ (year-end
    adjustments) are left out; the month view only knows 1-12."""
    groups = LEDGER_INCOME_GROUPS + LEDGER_COST_GROUPS + LEDGER_EXPENSE_GROUPS + LEDGER_FINANCIAL_GROUPS
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            f"""
            SELECT mp.Ejercicio, mp.Periodo, LEFT(cu.Codigo, 4), cu.Nombre,
                   SUM(CASE WHEN mp.TipoMovto = 0 THEN mp.Importe ELSE -mp.Importe END)
            FROM {LEDGER_DATABASE}.dbo.MovimientosPoliza mp
            JOIN {LEDGER_DATABASE}.dbo.Cuentas cu ON cu.Id = mp.IdCuenta
            WHERE mp.Periodo BETWEEN 1 AND 12
              AND mp.Ejercicio * 100 + mp.Periodo BETWEEN %s AND %s
              AND LEFT(cu.Codigo, 4) IN ({', '.join(['%s'] * len(groups))})
            GROUP BY mp.Ejercicio, mp.Periodo, LEFT(cu.Codigo, 4), cu.Nombre
            """,
            [date_from.year * 100 + date_from.month, date_to.year * 100 + date_to.month, *groups],
        )
        return cursor.fetchall()


def expense_category(account_name):
    name = (account_name or '').upper()
    return next((label for label, pattern in EXPENSE_CATEGORIES if pattern.search(name)), OTHER_EXPENSES)


def summarize_results(rows, keys):
    """Monthly operating results from fetch_ledger_results, one row per key
    ("YYYY-MM"). Income comes back positive, costs and expenses positive."""
    categories = [label for label, _ in EXPENSE_CATEGORIES] + [OTHER_EXPENSES]
    months = {k: {'month': k, 'ingresos': 0.0, 'costo': 0.0, 'financieros': 0.0,
                  'gastos': {c: 0.0 for c in categories}} for k in keys}
    for y, period, group, name, net_debit in rows:
        row = months.get(f'{y}-{period:02d}')
        if row is None:
            continue
        net_debit = net_debit or 0
        if group in LEDGER_INCOME_GROUPS:
            row['ingresos'] -= net_debit
        elif group in LEDGER_COST_GROUPS:
            row['costo'] += net_debit
        elif group in LEDGER_EXPENSE_GROUPS:
            row['gastos'][expense_category(name)] += net_debit
        else:
            row['financieros'] += net_debit
    for row in months.values():
        row['utilidad_operativa'] = row['ingresos'] - row['costo'] - sum(row['gastos'].values())
        row['ingresos'], row['costo'], row['financieros'], row['utilidad_operativa'] = (
            round(v, 2) for v in (row['ingresos'], row['costo'], row['financieros'], row['utilidad_operativa']))
        row['gastos'] = {c: round(v, 2) for c, v in row['gastos'].items()}
    return [months[k] for k in keys]


def receivables_today():
    """Outstanding balance today and DSO over the last 365 days, both with IVA.
    ponytail: only invoices from the last year count - older unpaid ones are
    collection problems, not the normal cycle; widen the floor if asked."""
    today = date.today()
    facturas = CommissionRepository.fetch_scoped_facturas(today - timedelta(days=365), today)
    pending = sum(f['CPENDIENTE'] or 0 for f in facturas)
    sold = sum(f['CTOTAL'] or 0 for f in facturas)
    return {'pendiente': round(pending, 2), 'dias_cobro': round(pending / sold * 365, 1) if sold else None}


def calculate_sales(year, month):
    next_month = date(year + month // 12, month % 12 + 1, 1)
    result = summarize(
        fetch_month_lines(date(year - 1, 1, 1), next_month),
        year, month, CommissionRepository.fetch_brand_names(),
    )
    corte = calculate_corte_de_caja(date(year, month, 1), next_month - timedelta(days=1))
    result['month'] = f'{year}-{month:02d}'
    result['resultados'] = summarize_results(
        fetch_ledger_results(date(year - 1, 1, 1), date(year, month, 1)),
        [m['month'] for m in result['months']],
    )
    result['cobrado'] = {z: round(float(v), 2) for z, v in corte['zone_totals'].items()}
    result['cuentas_por_cobrar'] = receivables_today()
    return result

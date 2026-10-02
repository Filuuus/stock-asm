"""Sales BI for management: monthly sales, gross margin, zone and brand mix.

What counts as a sale is the commissions / Corte de Caja rule: Facturas
(CIDDOCUMENTODE 4), not cancelled, in the ZONE_SCOPE zones. Returns (5) and
credit notes (7) net against sales in the month they were issued. Amounts are
before IVA: line CNETO minus discounts, which equals the header CTOTAL minus
CIMPUESTO1 (checked on Aug 2026). Cost is the ERP's CCOSTOESPECIFICO per line;
services carry no cost. Read-only, like every ERP access in this project.
"""
from collections import defaultdict
from datetime import date, timedelta

from django.db import connections

from commissions.services import (
    DEVOLUCION_DOC_TYPE,
    FACTURA_DOC_TYPE,
    NOTA_CREDITO_DOC_TYPE,
    ZONE_SCOPE,
    CommissionRepository,
)
from corte_de_caja.services import calculate_corte_de_caja

NO_BRAND = 'Sin marca'


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
    result['cobrado'] = {z: round(float(v), 2) for z, v in corte['zone_totals'].items()}
    result['cuentas_por_cobrar'] = receivables_today()
    return result

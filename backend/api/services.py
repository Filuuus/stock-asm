from django.core.cache import cache
from django.db import connections
from .models import AdmClasificacionesValores, AdmProductos
from catalog.services import get_images_by_codes, get_public_price_codes
from commissions.services import _classify_line

# Values that mean "no supplier assigned" rather than a real brand.
NO_BRAND_VALUES = {'(Ninguna)', '(Ninguno)'}
GENERAL_WAREHOUSE_ID = 4
FACTURA_DOC_TYPE = 4
DEVOLUCION_DOC_TYPE = 5

class InventoryRepository:
    @staticmethod
    def fetch_inventory():
        return list(
            AdmProductos.objects.exclude(CIDPRODUCTO=0).values(
                'CIDPRODUCTO',
                'CCODIGOPRODUCTO',
                'CNOMBREPRODUCTO',
                'CPRECIO1',
                'CIDVALORCLASIFICACION1',
                'CIDVALORCLASIFICACION2',
                'CTIPOPRODUCTO',
            )
        )

    @staticmethod
    def fetch_stock():
        """{product id: units} in ALMACEN GENERAL for the latest fiscal year
        (formula verified in the ERP schema notes; the other warehouses are
        people's trucks, not stock for sale)."""
        with connections['erp'].cursor() as cursor:
            cursor.execute(
                """
                SELECT CIDPRODUCTO,
                       (CENTRADASINICIALES + CENTRADASPERIODO12) - (CSALIDASINICIALES + CSALIDASPERIODO12)
                FROM admExistenciaCosto
                WHERE CIDALMACEN = %s
                  AND CIDEJERCICIO = (SELECT MAX(CIDEJERCICIO) FROM admExistenciaCosto WHERE CIDALMACEN = %s)
                """,
                [GENERAL_WAREHOUSE_ID, GENERAL_WAREHOUSE_ID],
            )
            return dict(cursor.fetchall())

    @staticmethod
    def fetch_units_sold():
        """{product id: units invoiced minus returned} over the last 12 months."""
        with connections['erp'].cursor() as cursor:
            cursor.execute(
                """
                SELECT m.CIDPRODUCTO,
                       SUM(CASE WHEN d.CIDDOCUMENTODE = %s THEN m.CUNIDADES ELSE -m.CUNIDADES END)
                FROM admMovimientos m
                JOIN admDocumentos d ON d.CIDDOCUMENTO = m.CIDDOCUMENTO
                WHERE d.CIDDOCUMENTODE IN (%s, %s) AND d.CCANCELADO = 0
                  AND d.CFECHA >= DATEADD(month, -12, GETDATE())
                GROUP BY m.CIDPRODUCTO
                """,
                [FACTURA_DOC_TYPE, FACTURA_DOC_TYPE, DEVOLUCION_DOC_TYPE],
            )
            return dict(cursor.fetchall())

    @staticmethod
    def fetch_brand_names():
        return dict(
            AdmClasificacionesValores.objects.values_list(
                'CIDVALORCLASIFICACION', 'CVALORCLASIFICACION'
            )
        )

def get_inventory_catalog(is_worker):
    cache_key = 'inventory_catalog'
    data = cache.get(cache_key)
    if data is None:
        data = InventoryRepository.fetch_inventory()

        brand_names = InventoryRepository.fetch_brand_names()
        stock = InventoryRepository.fetch_stock()
        units_sold = InventoryRepository.fetch_units_sold()
        # 1 = best seller; products with no net sales get no rank.
        ranked = sorted((u, pid) for pid, u in units_sold.items() if u > 0)
        sold_rank = {pid: i for i, (_, pid) in enumerate(reversed(ranked), start=1)}
        for product in data:
            # Commission categories double as the catalog's Categoría. An
            # empty zero-commission set: that list is a pay rule, not a kind.
            product['category'] = _classify_line(product, brand_names, set())
            brand = brand_names.get(product.pop('CIDVALORCLASIFICACION1'))
            product['brand'] = brand if brand and brand not in NO_BRAND_VALUES else None
            line = brand_names.get(product.pop('CIDVALORCLASIFICACION2'))
            product['line'] = line if line and line not in NO_BRAND_VALUES else None
            del product['CTIPOPRODUCTO']
            product['stock'] = stock.get(product['CIDPRODUCTO'], 0) or 0
            product['sold_rank'] = sold_rank.get(product['CIDPRODUCTO'])

        images_by_code = get_images_by_codes([p['CCODIGOPRODUCTO'] for p in data])
        for product in data:
            product['images'] = images_by_code.get(product['CCODIGOPRODUCTO'], [])

        cache.set(cache_key, data, timeout=600)

    # Price visibility is role/resource-aware and computed per request, never
    # cached - the cached catalog above is shared across every requester
    # regardless of who's asking. Prices are private to company workers by
    # default; a product is public only via an explicit ProductPriceVisibility
    # row (see catalog.models - the owner's 2026-09 decision).
    public_codes = get_public_price_codes()
    result = []
    for product in data:
        visible = is_worker or product['CCODIGOPRODUCTO'] in public_codes
        result.append({
            **product,
            'CPRECIO1': product['CPRECIO1'] if visible else None,
            'price_visible': visible,
            # Staff see units; the public only whether there is any.
            'stock': product['stock'] if is_worker else None,
            'in_stock': product['stock'] > 0,
        })
    return result

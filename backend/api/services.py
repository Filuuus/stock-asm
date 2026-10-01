import json
import os
import unicodedata
from collections import defaultdict
from functools import lru_cache

from django.conf import settings
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
    gea = _gea_products() if is_worker else {}
    result = []
    for product in data:
        note = (gea.get(product['CCODIGOPRODUCTO']) or {}).get('note') or {}
        visible = is_worker or product['CCODIGOPRODUCTO'] in public_codes
        result.append({
            **product,
            'CPRECIO1': product['CPRECIO1'] if visible else None,
            'price_visible': visible,
            # Staff see units; the public only whether there is any.
            'stock': product['stock'] if is_worker else None,
            'in_stock': product['stock'] > 0,
            # Staff only: GEA no longer supplies it (and what replaces it).
            'discontinued': {'replacement': note.get('replacement')} if note.get('not_orderable') else None,
        })
    return result


# GEA portal data (backend/exports/gea, gitignored - pulled from GEA's dealer
# portal and parsed by parse_gea.py). Optional: without the file the product
# page just shows the ERP data.
GEA_PRODUCTS_FILE = settings.BASE_DIR / 'exports' / 'gea' / 'gea_products.json'


@lru_cache(maxsize=1)
def _load_gea(mtime):
    with open(GEA_PRODUCTS_FILE, encoding='utf-8') as f:
        return json.load(f)


def _gea_products():
    try:
        return _load_gea(os.path.getmtime(GEA_PRODUCTS_FILE))
    except OSError:
        return {}


# GEA's exploded drawings, downloaded unresized (the hotspots are in their pixels).
DRAWINGS_DIR = settings.BASE_DIR.parent / 'frontend' / 'public' / 'products' / 'ets'


def _local_drawing(drawing):
    """Our copy of the drawing, or None when GEA's server didn't have it
    (13 referenced drawings 404 there)."""
    if not drawing or not drawing.get('img'):
        return None
    name = os.path.basename(drawing['img'])
    if not (DRAWINGS_DIR / name).exists():
        return None
    return {'img': f'/products/ets/{name}', 'hotspots': drawing['hotspots']}


def _plain_code(code):
    """ERP codes sometimes carry a regional letter (7021-2764-010W) that GEA's
    own code doesn't."""
    return code.rstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZ')


def _drawings_containing(gea_products):
    """Reverse of the parts lists: GEA part code -> [(our assembly code, pos, qty)].
    Rebuilt per request - ~20k rows, cheap."""
    index = defaultdict(list)
    for parent, gea in gea_products.items():
        rows = (gea.get('drawing') or {}).get('parts') or gea.get('parts', [])
        for r in rows:
            index[r['code']].append((parent, r['pos'], r['qty']))
    return index


def _appears_in(code, gea_code, by_code, summary):
    """Our assemblies whose parts list (and drawing, when we have it) include
    this part - the "where is this piece used" lookup."""
    gea = _gea_products()
    index = _drawings_containing(gea)
    out, seen = [], set()
    for parent, pos, qty in index.get(gea_code, []):
        if parent == code or parent in seen or parent not in by_code:
            continue
        seen.add(parent)
        out.append({
            'pos': pos, 'qty': qty,
            'has_drawing': _local_drawing(gea[parent].get('drawing')) is not None,
            'parent': summary(by_code[parent]),
        })
    return out


def _staff_note(note, link):
    if not note:
        return None
    replacement = note['replacement'] and link({'code': note['replacement'], 'desc': ''})
    return {**note, 'replacement_ours': replacement['ours'] if replacement else []}


def get_product_detail(code, is_worker):
    catalog = get_inventory_catalog(is_worker)
    by_code = {p['CCODIGOPRODUCTO']: p for p in catalog}
    product = by_code.get(code)
    if product is None:
        return None

    def summary(p):
        return {k: p[k] for k in ('CCODIGOPRODUCTO', 'CNOMBREPRODUCTO', 'CPRECIO1', 'price_visible', 'in_stock', 'images')}

    gea = _gea_products().get(code)
    appears_in = _appears_in(code, gea['gea_code'] if gea else _plain_code(code), by_code, summary)
    if gea is None:
        return {**product, 'appears_in': appears_in, 'gea': None}

    ours = defaultdict(list)
    for p in catalog:
        ours[_plain_code(p['CCODIGOPRODUCTO'])].append(p)

    def link(row):
        # Our own products for that GEA code, so the page can link to them.
        return {**row, 'ours': [summary(p) for p in ours.get(row['code'], []) if p['CCODIGOPRODUCTO'] != code]}

    # GEA's where-used list, minus the assemblies already shown with their drawing.
    shown = {_plain_code(a['parent']['CCODIGOPRODUCTO']) for a in appears_in}
    drawing = gea.get('drawing')
    return {
        **product,
        'appears_in': appears_in,
        'gea': {
            'code': gea['gea_code'],
            'desc': gea['desc'],
            'parts': [link(r) for r in (drawing or {}).get('parts') or gea.get('parts', [])],
            'drawing': _local_drawing(drawing),
            'spare_parts': [link(r) for r in gea.get('spare_parts', [])],
            'used_in': [link(r) for r in gea.get('used_in', []) if r['code'] not in shown],
            # GEA manual document numbers per language.
            'manuals': gea.get('manuals', []),
            # GEA's service interval; public (owner, 2026-10-01).
            'service': gea.get('service') and {
                'rules': gea['service']['rules'],
                'in_assemblies': [link(r) for r in gea['service']['in_assemblies']],
            },
            # "Not orderable" / replacement notes are internal (owner, 2026-10-01).
            'note': _staff_note(gea.get('note'), link) if is_worker else None,
        },
    }


def _fold(text):
    """Lowercase, no accents, no dashes - so "7041 2717", "70412717" and
    "vastago" all match."""
    text = unicodedata.normalize('NFD', text.lower())
    return ''.join(c for c in text if unicodedata.category(c) != 'Mn').replace('-', '')


def search_gea_parts(query, is_worker, limit=20):
    """Parts from GEA's parts lists that we don't sell, matched by code or
    description, each with the products of ours they appear in. Lets someone
    holding a GEA part number find the machine (and drawing) it belongs to."""
    terms = _fold(query).split()
    if not terms or sum(len(t) for t in terms) < 3:
        return []
    catalog = get_inventory_catalog(is_worker)
    by_code = {p['CCODIGOPRODUCTO']: p for p in catalog}
    sold = {_plain_code(c) for c in by_code}

    def summary(p):
        return {k: p[k] for k in ('CCODIGOPRODUCTO', 'CNOMBREPRODUCTO', 'images')}

    descs = {}
    for gea in _gea_products().values():
        for r in (gea.get('drawing') or {}).get('parts') or gea.get('parts', []):
            descs.setdefault(r['code'], r['desc'])
    results = []
    for code, desc in descs.items():
        if code in sold or not all(t in _fold(f'{code} {desc}') for t in terms):
            continue
        appears_in = _appears_in(None, code, by_code, summary)
        if appears_in:
            results.append({'code': code, 'desc': desc, 'appears_in': appears_in})
        if len(results) >= limit:
            break
    return results

import json
import os
import re
import unicodedata
from collections import defaultdict
from functools import lru_cache

from django.conf import settings
from django.core.cache import cache
from django.db import connections
from django.utils.text import slugify
from .models import AdmClasificacionesValores, AdmProductos
from catalog.models import ProductDescription
from catalog.services import get_images_by_codes
from commissions.services import _classify_line

# Public catalog rules (owner, 2026-10-13): logged-out visitors only see products
# in stock; prices only for these categories (not chemicals, fans, services -
# too many close competitors) and only while in stock; no part numbers anywhere
# (customers would buy the exact piece elsewhere); and the brand only when it's
# a real brand, never the distributor we buy from.
PUBLIC_PRICE_CATEGORIES = {'R', 'R_NW', 'B'}
PUBLIC_BRANDS = {
    'GEA FARM TECHNOLOGIES': 'GEA',
    'BIONAT-SANO, SA DE CV': 'Bionat',
    'NORTH WEST RUBBER': 'North West Rubber',
    'VES-ARTEX': 'VES-Artex',
}
NO_PUBLIC_BRAND_CATEGORIES = {'R_CHEM'}
# Out of stock but still public as "Sobre pedido" (management wants to push
# them, 2026-10-13): mats and fans always, Bionat only if sold in the last 12
# months (the rest is mostly discontinued).
ON_ORDER_CATEGORIES = {'R_NW', 'R_FAN'}
# GEA-style codes inside names ("VALVULA (7050-1935-000)", "JGO 4X7023-2721-060").
CODE_IN_TEXT_RE = re.compile(r'\s*\(?(?<!\d)\d{4,5}-\d{4}-\d{3,4}[A-Z]?(?!\d)\)?')
# Keys that carry a part number (ours, GEA's, or a GEA document number).
CODE_KEYS = {'CCODIGOPRODUCTO', 'code', 'gea_code', 'replacement'}
TEXT_KEYS = {'CNOMBREPRODUCTO', 'desc', 'name', 'description'}
RELATED_LIMIT = 8

# The catalog's Bionat Línea: the whole brand is one category, split into a
# few big groups by product type (the ERP's line and the commission split are
# pay rules, not kinds). First match on the name wins; drafted from
# bionatsano.com.mx's descriptions. Finer levels (species, stage) can come later.
BIONAT_TYPES = [
    ('ENERGIZER', 'Aditivos'),
    ('CONCENTRADO', 'Alimentos'),
    ('MIPRO', 'Minerales y premezclas'),
    ('SUSAN', 'Minerales y premezclas'),
    ('PREMIX', 'Minerales y premezclas'),
    ('SANOLAC', 'Sustitutos de leche'),
    ('MILSAN', 'Sustitutos de leche'),
    ('LATTECCINO', 'Sustitutos de leche'),
    ('FORMULA LACTEA', 'Sustitutos de leche'),
    ('SUSTITUTO', 'Sustitutos de leche'),
    ('LEMMI', 'Sustitutos de leche'),
    # Starters, concentrates and complete feeds.
    ('MEGGI', 'Alimentos'),
    ('PREKERN', 'Alimentos'),
    ('BONNI', 'Alimentos'),
    ('OVISAN', 'Alimentos'),
]


def _bionat_type(name):
    name = (name or '').upper()
    return next((t for marker, t in BIONAT_TYPES if marker in name), 'Aditivos')

# Mats sold in many versions show as one product per family, with options on its page.
# Names read per the user (2026-10-15): "<width> X 6" in feet, I<sides with interlock>,
# F<feet of interlocking edge>, D/I = right/left (GEA's descriptions say (R)/(L)).
PEBBLETOP_RE = re.compile(r'EN CLAVAMIENTO (\d) X 6 I(\d) F(\d+)(?: ([DI]))?')
INTERLOCK_EDGES = {
    (4, 20): 'En los 4 lados', (4, 16): '2 lados largos y 1 corto', (4, 14): '2 lados cortos y 1 largo',
    (4, 12): '2 lados largos', (4, 10): '1 lado largo y 1 corto', (4, 8): '2 lados cortos',
    (2, 4): '2 lados cortos', (1, 2): '2 lados cortos',
}


def mat_variant(name):
    """{'family', 'options'} for a mat that comes in several versions, else None."""
    name = (name or '').upper()
    m = PEBBLETOP_RE.search(name)
    if m:
        width, sides, feet, hand = int(m[1]), int(m[2]), int(m[3]), m[4]
        interlock = 'Sin interlock' if sides == 0 else INTERLOCK_EDGES.get((width, feet), f'I{sides} F{feet}')
        if hand:
            interlock += ' (derecha)' if hand == 'D' else ' (izquierda)'
        # sort: narrow to wide, then most interlock first.
        return {'family': 'PebbleTop', 'options': {'Ancho': f'{width} pie' + 's' * (width > 1), 'Interlock': interlock},
                'sort': [width, -feet, hand or '']}
    if 'MAXGRIP' in name:
        bare = 'SIN INTERLOCK' in name
        return {'family': 'MaxGrip', 'options': {'Interlock': 'Sin interlock' if bare else 'En los 4 lados'},
                'sort': [int(bare)]}
    return None


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
                'CIMPUESTO1',
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
    def fetch_product_activity(code):
        """Staff box on the product page: stock in every warehouse (incl. the
        technicians' trucks), units invoiced minus returned over 12 months, and
        the last invoice date."""
        with connections['erp'].cursor() as cursor:
            cursor.execute(
                """
                SELECT a.CNOMBREALMACEN,
                       (e.CENTRADASINICIALES + e.CENTRADASPERIODO12) - (e.CSALIDASINICIALES + e.CSALIDASPERIODO12)
                FROM admExistenciaCosto e
                JOIN admAlmacenes a ON a.CIDALMACEN = e.CIDALMACEN
                JOIN admProductos p ON p.CIDPRODUCTO = e.CIDPRODUCTO
                WHERE p.CCODIGOPRODUCTO = %s
                  AND e.CIDEJERCICIO = (SELECT MAX(CIDEJERCICIO) FROM admExistenciaCosto)
                """,
                [code],
            )
            warehouses = sorted(
                ({'name': name.strip(), 'units': units} for name, units in cursor.fetchall() if units),
                key=lambda w: -w['units'],
            )
            cursor.execute(
                """
                SELECT SUM(CASE WHEN d.CFECHA >= DATEADD(month, -12, GETDATE())
                                THEN CASE WHEN d.CIDDOCUMENTODE = %s THEN m.CUNIDADES ELSE -m.CUNIDADES END END),
                       MAX(CASE WHEN d.CIDDOCUMENTODE = %s THEN d.CFECHA END)
                FROM admMovimientos m
                JOIN admDocumentos d ON d.CIDDOCUMENTO = m.CIDDOCUMENTO
                JOIN admProductos p ON p.CIDPRODUCTO = m.CIDPRODUCTO
                WHERE p.CCODIGOPRODUCTO = %s AND d.CIDDOCUMENTODE IN (%s, %s) AND d.CCANCELADO = 0
                """,
                [FACTURA_DOC_TYPE, FACTURA_DOC_TYPE, code, FACTURA_DOC_TYPE, DEVOLUCION_DOC_TYPE],
            )
            sold_12m, last_sale = cursor.fetchone()
        return {
            'warehouses': warehouses,
            'sold_12m': sold_12m or 0,
            'last_sale': last_sale.date().isoformat() if last_sale else None,
        }

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

def get_inventory_catalog(is_worker, raw=False):
    """The catalog as the API serves it. raw=True keeps the codes (server-side
    use only - see _catalog)."""
    if not raw and not is_worker:
        return scrub(_catalog(False))
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
            category = _classify_line(product, brand_names, set())
            # Mipro and Bovifit are Bionat; they only differ in commission rate.
            product['category'] = 'B' if category.startswith('B') else category
            brand = brand_names.get(product.pop('CIDVALORCLASIFICACION1'))
            product['brand'] = brand if brand and brand not in NO_BRAND_VALUES else None
            line = brand_names.get(product.pop('CIDVALORCLASIFICACION2'))
            product['line'] = line if line and line not in NO_BRAND_VALUES else None
            if product['category'] == 'B':
                product['line'] = _bionat_type(product['CNOMBREPRODUCTO'])
            # The public id: the URL, cart and quotes use it instead of the code.
            product['key'] = str(product['CIDPRODUCTO'])
            # Readable URL tail (/producto/86-pulsador-vacopuls-...), never with a code.
            product['slug'] = slugify(CODE_IN_TEXT_RE.sub('', product['CNOMBREPRODUCTO'] or ''))[:60].strip('-')
            del product['CTIPOPRODUCTO']
            product['stock'] = stock.get(product['CIDPRODUCTO'], 0) or 0
            product['sold_rank'] = sold_rank.get(product['CIDPRODUCTO'])
            product['variant'] = mat_variant(product['CNOMBREPRODUCTO']) if product['category'] == 'R_NW' else None

        images_by_code = get_images_by_codes([p['CCODIGOPRODUCTO'] for p in data])
        for product in data:
            product['images'] = images_by_code.get(product['CCODIGOPRODUCTO'], [])

        cache.set(cache_key, data, timeout=600)

    return _apply_role(data, is_worker)


def _apply_role(data, is_worker):
    """Per request, never cached: the cached catalog is shared by every role.
    Staff see everything; the public only what's in stock or on order
    (ON_ORDER_CATEGORIES), priced per PUBLIC_PRICE_CATEGORIES. Codes are still here - _scrub removes them."""
    gea = _gea_products() if is_worker else {}
    result = []
    for product in data:
        in_stock = product['stock'] > 0
        on_order = not in_stock and (product['category'] in ON_ORDER_CATEGORIES
                                     or (product['category'] == 'B' and product['sold_rank'] is not None))
        if not is_worker and not in_stock and not on_order:
            continue
        note = (gea.get(product['CCODIGOPRODUCTO']) or {}).get('note') or {}
        visible = is_worker or product['category'] in PUBLIC_PRICE_CATEGORIES
        brand = product['brand']
        if not is_worker:
            brand = None if product['category'] in NO_PUBLIC_BRAND_CATEGORIES else PUBLIC_BRANDS.get(brand)
        result.append({
            **product,
            'CPRECIO1': product['CPRECIO1'] if visible else None,
            # What the customer pays: CPRECIO1 is before IVA, and the rate is the
            # product's own (16% parts, 0% Bionat feed; matches every invoice).
            'price': _with_iva(product['CPRECIO1'], product['CIMPUESTO1']) if visible else None,
            'price_visible': visible,
            'brand': brand,
            # Staff see units; the public only whether there is any.
            'stock': product['stock'] if is_worker else None,
            'in_stock': in_stock,
            'on_order': on_order,
            # Staff only: GEA no longer supplies it (and what replaces it).
            'discontinued': {'replacement': note.get('replacement')} if note.get('not_orderable') else None,
        })
    return result


def _with_iva(price, rate):
    return round(price * (1 + (rate or 0) / 100), 2) if price else price


def _catalog(is_worker):
    """The role's catalog with codes kept, for use inside the server."""
    return get_inventory_catalog(is_worker, raw=True)


def scrub(obj):
    """Removes part numbers from anything about to reach the public: code
    fields go blank, codes inside names and descriptions are cut out."""
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    if isinstance(obj, dict):
        return {
            k: None if k in CODE_KEYS else
            CODE_IN_TEXT_RE.sub('', v).strip() if k in TEXT_KEYS and isinstance(v, str) else scrub(v)
            for k, v in obj.items()
        }
    return obj


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


# GEA's exploded drawings, downloaded unresized (the hotspots are in their pixels),
# stored under random names (GEA names them by part number): the
# hide_media_names command keeps the map.
DRAWINGS_DIR = settings.BASE_DIR.parent / 'frontend' / 'public' / 'products' / 'ets'
DRAWING_NAMES_FILE = settings.BASE_DIR / 'exports' / 'gea' / 'drawing_names.json'


@lru_cache(maxsize=1)
def _load_drawing_names(mtime):
    return json.loads(DRAWING_NAMES_FILE.read_text())


def _local_drawing(drawing):
    """Our copy of the drawing, or None when GEA's server didn't have it
    (13 referenced drawings 404 there)."""
    if not drawing or not drawing.get('img'):
        return None
    try:
        name = _load_drawing_names(os.path.getmtime(DRAWING_NAMES_FILE)).get(os.path.basename(drawing['img']))
    except OSError:
        return None
    if not name or not (DRAWINGS_DIR / name).exists():
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


def get_product_detail(key, is_worker):
    catalog = _catalog(is_worker)
    by_code = {p['CCODIGOPRODUCTO']: p for p in catalog}
    product = next((p for p in catalog if p['key'] == key), None)
    if product is None:
        return None
    code = product['CCODIGOPRODUCTO']
    detail = _product_detail(product, code, catalog, by_code, is_worker)
    description = ProductDescription.objects.filter(producto_codigo=code).values_list('text', flat=True).first()
    detail.update(description=description, related=_related(product, catalog), variants=_variants(product, catalog))
    return detail if is_worker else scrub(detail)


def summary(p):
    return {k: p[k] for k in ('key', 'slug', 'CCODIGOPRODUCTO', 'CNOMBREPRODUCTO', 'CPRECIO1', 'price',
                              'price_visible', 'in_stock', 'on_order', 'images')}


def _related(product, catalog):
    """Same category and line: in stock, best sellers and photographed first."""
    same = [p for p in catalog if p['key'] != product['key']
            and p['category'] == product['category'] and p['line'] == product['line']]
    same.sort(key=lambda p: (not p['in_stock'], p['sold_rank'] or float('inf'), not p['images']))
    return [summary(p) for p in same[:RELATED_LIMIT]]


def _variants(product, catalog):
    """The versions of the product's family the role can see, one per set of options: this
    product for its own, else in stock first, then the best seller. Empty if it has no family."""
    family = (product.get('variant') or {}).get('family')
    if not family:
        return []
    chosen = {}
    rank = lambda p: (p['key'] != product['key'], not p['in_stock'], p['sold_rank'] or float('inf'), int(p['key']))
    for p in sorted((p for p in catalog if (p.get('variant') or {}).get('family') == family), key=rank):
        chosen.setdefault(tuple(p['variant']['options'].items()), p)
    return [{'key': p['key'], 'slug': p['slug'], 'options': p['variant']['options'], 'price': p['price'],
             'in_stock': p['in_stock'], 'on_order': p['on_order']}
            for p in sorted(chosen.values(), key=lambda p: p['variant']['sort'])]


def _product_detail(product, code, catalog, by_code, is_worker):

    gea = _gea_products().get(code)
    appears_in = _appears_in(code, gea['gea_code'] if gea else _plain_code(code), by_code, summary)
    # Staff only, read live (never cached: it's per product and per role).
    staff = InventoryRepository.fetch_product_activity(code) if is_worker else None
    if gea is None:
        return {**product, 'appears_in': appears_in, 'staff': staff, 'gea': None}

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
        'staff': staff,
        'gea': {
            'code': gea['gea_code'],
            'desc': gea['desc'],
            'parts': [link(r) for r in (drawing or {}).get('parts') or gea.get('parts', [])],
            'drawing': _local_drawing(drawing),
            'spare_parts': [link(r) for r in gea.get('spare_parts', [])],
            'used_in': [link(r) for r in gea.get('used_in', []) if r['code'] not in shown],
            # GEA manual document numbers per language; staff only, a
            # document number identifies the machine just like a part number.
            'manuals': gea.get('manuals', []) if is_worker else [],
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
    catalog = _catalog(is_worker)
    by_code = {p['CCODIGOPRODUCTO']: p for p in catalog}
    sold = {_plain_code(c) for c in by_code}

    def summary(p):
        return {k: p[k] for k in ('key', 'slug', 'CCODIGOPRODUCTO', 'CNOMBREPRODUCTO', 'images')}

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

"""SimpleTestCase only: a database test would make Django try to create a
test database on the ERP server."""

from unittest.mock import patch

from django.test import SimpleTestCase

from .services import InventoryRepository, get_inventory_catalog, get_product_detail, search_gea_parts


def producto(pid, code, stock_units):
    return {
        'CIDPRODUCTO': pid, 'CCODIGOPRODUCTO': code, 'CNOMBREPRODUCTO': 'PEZONERA',
        'CPRECIO1': 100.0, 'CIDVALORCLASIFICACION1': 1,
        'CIDVALORCLASIFICACION2': 2, 'CTIPOPRODUCTO': 1,
    }, stock_units


class InventoryCatalogTests(SimpleTestCase):
    def catalog(self, is_worker):
        rows = [producto(1, 'A', 5.0), producto(2, 'B', 0.0), producto(3, 'C', -1.0)]
        with patch('api.services.cache') as cache, \
                patch.object(InventoryRepository, 'fetch_inventory', return_value=[r for r, _ in rows]), \
                patch.object(InventoryRepository, 'fetch_brand_names', return_value={1: 'GEA', 2: '(Ninguna)'}), \
                patch.object(InventoryRepository, 'fetch_stock', return_value={r['CIDPRODUCTO']: s for r, s in rows}), \
                patch.object(InventoryRepository, 'fetch_units_sold', return_value={1: 3.0, 2: 9.0, 3: -1.0}), \
                patch('api.services.get_images_by_codes', return_value={}), \
                patch('api.services.get_public_price_codes', return_value=set()):
            cache.get.return_value = None
            return {p['CIDPRODUCTO']: p for p in get_inventory_catalog(is_worker)}

    def test_staff_see_units_public_only_availability(self):
        staff, public = self.catalog(True), self.catalog(False)
        self.assertEqual([staff[i]['stock'] for i in (1, 2, 3)], [5.0, 0.0, -1.0])
        self.assertEqual([public[i]['stock'] for i in (1, 2, 3)], [None, None, None])
        self.assertEqual([public[i]['in_stock'] for i in (1, 2, 3)], [True, False, False])

    def test_category_line_and_sales_rank(self):
        staff = self.catalog(True)
        self.assertEqual(staff[1]['category'], 'R')
        self.assertIsNone(staff[1]['line'])  # "(Ninguna)" means no line
        self.assertEqual([staff[i]['sold_rank'] for i in (1, 2, 3)], [2, 1, None])


class ProductDetailTests(SimpleTestCase):
    GEA = {'7041-2700-550': {
        'gea_code': '7041-2700-550', 'desc': 'Pulsador', 'path': [],
        'parts': [{'pos': '0020', 'qty': 1.0, 'code': '7021-2764-010', 'desc': 'Pieza'}],
        'note': {'text': 'Nota', 'not_orderable': True, 'replacement': None},
    }}

    def detail(self, is_worker):
        catalog = [
            {'CCODIGOPRODUCTO': '7041-2700-550', 'CNOMBREPRODUCTO': 'PULSADOR', 'CPRECIO1': 1.0,
             'price_visible': True, 'in_stock': True, 'images': []},
            # Our code carries a regional letter; GEA's doesn't.
            {'CCODIGOPRODUCTO': '7021-2764-010W', 'CNOMBREPRODUCTO': 'PIEZA', 'CPRECIO1': None,
             'price_visible': False, 'in_stock': False, 'images': []},
        ]
        with patch('api.services.get_inventory_catalog', return_value=catalog), \
                patch('api.services._gea_products', return_value=self.GEA):
            return get_product_detail('7041-2700-550', is_worker)

    def test_part_lists_the_assemblies_it_appears_in(self):
        catalog = [
            {'CCODIGOPRODUCTO': '7041-2700-550', 'CNOMBREPRODUCTO': 'PULSADOR', 'CPRECIO1': 1.0,
             'price_visible': True, 'in_stock': True, 'images': []},
            {'CCODIGOPRODUCTO': '7021-2764-010W', 'CNOMBREPRODUCTO': 'PIEZA', 'CPRECIO1': None,
             'price_visible': False, 'in_stock': False, 'images': []},
        ]
        # The part has no GEA data of its own; it's found through the pulsator's list.
        with patch('api.services.get_inventory_catalog', return_value=catalog), \
                patch('api.services._gea_products', return_value=self.GEA):
            part = get_product_detail('7021-2764-010W', True)
        self.assertEqual([(a['parent']['CCODIGOPRODUCTO'], a['pos']) for a in part['appears_in']],
                         [('7041-2700-550', '0020')])

    def test_links_parts_to_our_products_and_hides_notes_from_public(self):
        staff, public = self.detail(True), self.detail(False)
        self.assertEqual([p['CCODIGOPRODUCTO'] for p in staff['gea']['parts'][0]['ours']], ['7021-2764-010W'])
        self.assertTrue(staff['gea']['note']['not_orderable'])
        self.assertIsNone(public['gea']['note'])


class GeaPartSearchTests(SimpleTestCase):
    GEA = {'7041-2700-550': {'gea_code': '7041-2700-550', 'desc': 'Pulsador', 'parts': [
        {'pos': '0020', 'qty': 1.0, 'code': '7041-2717-010', 'desc': 'Vástago de embolo'},
        {'pos': '0040', 'qty': 4.0, 'code': '7041-2745-010', 'desc': 'Disco presión'},
    ]}}
    CATALOG = [
        {'CCODIGOPRODUCTO': '7041-2700-550', 'CNOMBREPRODUCTO': 'PULSADOR', 'images': []},
        {'CCODIGOPRODUCTO': '7041-2745-010W', 'CNOMBREPRODUCTO': 'DISCO', 'images': []},
    ]

    def search(self, q):
        with patch('api.services.get_inventory_catalog', return_value=self.CATALOG), \
                patch('api.services._gea_products', return_value=self.GEA):
            return [(r['code'], [a['pos'] for a in r['appears_in']]) for r in search_gea_parts(q, False)]

    def test_finds_parts_we_dont_sell_by_code_or_accentless_word(self):
        self.assertEqual(self.search('70412717'), [('7041-2717-010', ['0020'])])
        self.assertEqual(self.search('vastago'), [('7041-2717-010', ['0020'])])
        # Sold parts (even with our regional letter) are left to the normal catalog search.
        self.assertEqual(self.search('disco'), [])

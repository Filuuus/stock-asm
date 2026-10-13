"""SimpleTestCase only: a database test would make Django try to create a
test database on the ERP server."""

from unittest.mock import patch

from django.test import SimpleTestCase

from .services import (InventoryRepository, _apply_role, _bionat_type, get_inventory_catalog, get_product_detail,
                       search_gea_parts)


def producto(pid, code, stock_units, name='PEZONERA'):
    return {
        'CIDPRODUCTO': pid, 'CCODIGOPRODUCTO': code, 'CNOMBREPRODUCTO': name,
        'CPRECIO1': 100.0, 'CIMPUESTO1': 16.0, 'CIDVALORCLASIFICACION1': 1,
        'CIDVALORCLASIFICACION2': 2, 'CTIPOPRODUCTO': 1,
    }, stock_units


class InventoryCatalogTests(SimpleTestCase):
    def catalog(self, is_worker):
        rows = [producto(1, 'A', 5.0, 'VALVULA (7050-1935-000)'), producto(2, 'B', 0.0), producto(3, 'C', -1.0, 'MIPRO 150')]
        with patch('api.services.cache') as cache, \
                patch.object(InventoryRepository, 'fetch_inventory', return_value=[r for r, _ in rows]), \
                patch.object(InventoryRepository, 'fetch_brand_names', return_value={1: 'GEA FARM TECHNOLOGIES', 2: '(Ninguna)'}), \
                patch.object(InventoryRepository, 'fetch_stock', return_value={r['CIDPRODUCTO']: s for r, s in rows}), \
                patch.object(InventoryRepository, 'fetch_units_sold', return_value={1: 3.0, 2: 9.0, 3: -1.0}), \
                patch('api.services.get_images_by_codes', return_value={}), \
                patch('api.services._gea_products', return_value={
                    'A': {'note': {'not_orderable': True, 'replacement': 'B'}}}):
            cache.get.return_value = None
            return {p['CIDPRODUCTO']: p for p in get_inventory_catalog(is_worker)}

    def test_staff_see_units_public_only_availability(self):
        staff, public = self.catalog(True), self.catalog(False)
        self.assertEqual([staff[i]['stock'] for i in (1, 2, 3)], [5.0, 0.0, -1.0])
        # The public never sees what's out of stock.
        self.assertEqual(list(public), [1])
        self.assertIsNone(public[1]['stock'])
        self.assertTrue(public[1]['in_stock'])

    def test_public_gets_no_part_numbers_and_only_real_brands(self):
        staff, public = self.catalog(True), self.catalog(False)
        self.assertEqual(staff[1]['CCODIGOPRODUCTO'], 'A')
        self.assertEqual(staff[1]['brand'], 'GEA FARM TECHNOLOGIES')
        self.assertEqual((public[1]['CCODIGOPRODUCTO'], public[1]['key']), (None, '1'))
        self.assertEqual(public[1]['CNOMBREPRODUCTO'], 'VALVULA')
        self.assertEqual(public[1]['brand'], 'GEA')
        # Refacciones in stock: the price is public, IVA included.
        self.assertEqual((public[1]['CPRECIO1'], public[1]['price']), (100.0, 116.0))

    def test_discontinued_flag_is_staff_only(self):
        self.assertEqual(self.catalog(True)[1]['discontinued'], {'replacement': 'B'})
        self.assertIsNone(self.catalog(True)[2]['discontinued'])
        self.assertIsNone(self.catalog(False)[1]['discontinued'])

    def test_public_prices_by_category(self):
        self.assertIsNone(_apply_role([self.row('R_CHEM')], False)[0]['CPRECIO1'])
        self.assertIsNone(_apply_role([self.row('R_CHEM')], False)[0]['brand'])
        # Bionat feed has no IVA.
        self.assertEqual(_apply_role([self.row('B', 0.0)], False)[0]['price'], 100.0)
        self.assertEqual(_apply_role([self.row('R_CHEM')], True)[0]['CPRECIO1'], 100.0)

    @staticmethod
    def row(category, iva=16.0, stock=1.0, sold_rank=None):
        return {'CCODIGOPRODUCTO': 'A', 'category': category, 'brand': 'GEA FARM TECHNOLOGIES',
                'CPRECIO1': 100.0, 'CIMPUESTO1': iva, 'stock': stock, 'sold_rank': sold_rank}

    def test_out_of_stock_mats_fans_and_selling_bionat_are_public_on_order(self):
        public = lambda row: _apply_role([row], False)
        self.assertEqual(public(self.row('R', stock=0)), [])
        self.assertEqual(public(self.row('B', stock=0)), [])  # no sales in 12 months
        bionat = public(self.row('B', stock=0, sold_rank=7))[0]
        self.assertEqual((bionat['on_order'], bionat['price']), (True, 116.0))
        self.assertTrue(public(self.row('R_NW', stock=0))[0]['on_order'])
        fan = public(self.row('R_FAN', stock=0))[0]
        self.assertEqual((fan['on_order'], fan['price']), (True, None))

    def test_bionat_types(self):
        self.assertEqual(_bionat_type('CONCENTRADO MIPRO PREN 400'), 'Alimentos')
        self.assertEqual(_bionat_type('MEGGI 100 E 25 KG'), 'Alimentos')
        self.assertEqual(_bionat_type('MIPRO ENERGIZER 25 KG'), 'Aditivos')
        self.assertEqual(_bionat_type('MIPRO 250 HM 25 KG'), 'Minerales y premezclas')
        self.assertEqual(_bionat_type('SANOLAC LAMB 2 KG'), 'Sustitutos de leche')

    def test_category_line_and_sales_rank(self):
        # Mipro is Bionat in the catalog (the split is only a commission rate).
        self.assertEqual(self.catalog(True)[3]['category'], 'B')
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
            {'key': '1', 'slug': 'pulsador', 'category': 'R', 'line': None, 'sold_rank': 1,
             'CCODIGOPRODUCTO': '7041-2700-550', 'CNOMBREPRODUCTO': 'PULSADOR', 'CPRECIO1': 1.0, 'price': 1.16,
             'price_visible': True, 'in_stock': True, 'on_order': False, 'images': []},
            # Our code carries a regional letter; GEA's doesn't.
            {'key': '2', 'slug': 'pieza', 'category': 'R', 'line': None, 'sold_rank': None,
             'CCODIGOPRODUCTO': '7021-2764-010W', 'CNOMBREPRODUCTO': 'PIEZA', 'CPRECIO1': None, 'price': None,
             'price_visible': False, 'in_stock': False, 'on_order': False, 'images': []},
        ]
        with patch('api.services._catalog', return_value=catalog), \
                patch('api.services.ProductDescription') as descriptions, \
                patch('api.services._gea_products', return_value=self.GEA), \
                patch.object(InventoryRepository, 'fetch_product_activity', return_value={'sold_12m': 5}) as activity:
            descriptions.objects.filter.return_value.values_list.return_value.first.return_value = \
                'Repuesto (7021-2764-010)'
            detail = get_product_detail('1', is_worker)
            # The ERP is only queried for staff.
            self.assertEqual(activity.called, is_worker)
            return detail

    def test_part_lists_the_assemblies_it_appears_in(self):
        catalog = [
            {'key': '1', 'slug': 'pulsador', 'category': 'R', 'line': None, 'sold_rank': 1,
             'CCODIGOPRODUCTO': '7041-2700-550', 'CNOMBREPRODUCTO': 'PULSADOR', 'CPRECIO1': 1.0, 'price': 1.16,
             'price_visible': True, 'in_stock': True, 'on_order': False, 'images': []},
            {'key': '2', 'slug': 'pieza', 'category': 'R', 'line': None, 'sold_rank': None,
             'CCODIGOPRODUCTO': '7021-2764-010W', 'CNOMBREPRODUCTO': 'PIEZA', 'CPRECIO1': None, 'price': None,
             'price_visible': False, 'in_stock': False, 'on_order': False, 'images': []},
        ]
        # The part has no GEA data of its own; it's found through the pulsator's list.
        with patch('api.services._catalog', return_value=catalog), \
                patch('api.services.ProductDescription') as descriptions, \
                patch('api.services._gea_products', return_value=self.GEA), \
                patch.object(InventoryRepository, 'fetch_product_activity', return_value={}):
            part = get_product_detail('2', True)
        self.assertEqual([(a['parent']['CCODIGOPRODUCTO'], a['pos']) for a in part['appears_in']],
                         [('7041-2700-550', '0020')])

    def test_links_parts_to_our_products_and_hides_notes_from_public(self):
        staff, public = self.detail(True), self.detail(False)
        self.assertEqual([p['CCODIGOPRODUCTO'] for p in staff['gea']['parts'][0]['ours']], ['7021-2764-010W'])
        self.assertTrue(staff['gea']['note']['not_orderable'])
        self.assertIsNone(public['gea']['note'])
        self.assertEqual(staff['staff'], {'sold_12m': 5})
        self.assertIsNone(public['staff'])
        # The public page links by key and never shows a code.
        part = public['gea']['parts'][0]
        self.assertEqual((public['gea']['code'], part['code'], part['ours'][0]['key']), (None, None, '2'))
        self.assertIsNone(part['ours'][0]['CCODIGOPRODUCTO'])

    def test_description_is_scrubbed_and_related_share_the_line(self):
        public = self.detail(False)
        self.assertEqual(public['description'], 'Repuesto')
        self.assertEqual([p['key'] for p in public['related']], ['2'])


class GeaPartSearchTests(SimpleTestCase):
    GEA = {'7041-2700-550': {'gea_code': '7041-2700-550', 'desc': 'Pulsador', 'parts': [
        {'pos': '0020', 'qty': 1.0, 'code': '7041-2717-010', 'desc': 'Vástago de embolo'},
        {'pos': '0040', 'qty': 4.0, 'code': '7041-2745-010', 'desc': 'Disco presión'},
    ]}}
    CATALOG = [
        {'key': '1', 'slug': 'pulsador', 'CCODIGOPRODUCTO': '7041-2700-550', 'CNOMBREPRODUCTO': 'PULSADOR', 'images': []},
        {'key': '2', 'slug': 'disco', 'CCODIGOPRODUCTO': '7041-2745-010W', 'CNOMBREPRODUCTO': 'DISCO', 'images': []},
    ]

    def search(self, q):
        with patch('api.services._catalog', return_value=self.CATALOG), \
                patch('api.services._gea_products', return_value=self.GEA):
            return [(r['code'], [a['pos'] for a in r['appears_in']]) for r in search_gea_parts(q, True)]

    def test_finds_parts_we_dont_sell_by_code_or_accentless_word(self):
        self.assertEqual(self.search('70412717'), [('7041-2717-010', ['0020'])])
        self.assertEqual(self.search('vastago'), [('7041-2717-010', ['0020'])])
        # Sold parts (even with our regional letter) are left to the normal catalog search.
        self.assertEqual(self.search('disco'), [])

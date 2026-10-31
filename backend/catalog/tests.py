"""Quote requests. These use the local database only (databases = {'default'}),
so no test database is created on the ERP server; the ERP catalog is mocked."""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings

from accounts.models import Profile
from catalog import quotes
from api.services import _catalog, _lines, get_inventory_catalog, get_product_detail
from catalog.models import HiddenProduct, ProductDescription, QuoteRequest, SpecialOrderProduct

CATALOG = [
    {'key': '1', 'CCODIGOPRODUCTO': 'A', 'CNOMBREPRODUCTO': 'PEZONERA (7050-1935-000)', 'price': 100.0, 'stock': 5.0,
     'in_stock': True, 'images': []},
    {'key': '2', 'CCODIGOPRODUCTO': 'B', 'CNOMBREPRODUCTO': 'JUNTA', 'price': 0.0, 'stock': 0.0,
     'in_stock': False, 'images': []},
]


def catalog(is_worker):
    # The public never gets prices from the catalog.
    return [{**p, 'price': p['price'] if is_worker else None} for p in CATALOG]


# In-memory cache: the form's rate limit must not count against the dev Redis.
@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
@patch('catalog.quotes._catalog', side_effect=catalog)
class QuoteRequestTests(TestCase):
    databases = {'default'}

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.manager = User.objects.create_user('gerencia', password='x')
        self.manager.profile.role = Profile.ROLE_MANAGEMENT
        self.manager.profile.save()
        self.seller = User.objects.create_user('vendedor', password='x')

    def send(self):
        return self.client.post('/api/solicitudes/', {
            'name': 'Cliente', 'phone': '33 1234 5678',
            'items': [{'key': '1', 'quantity': 2}, {'key': '2', 'quantity': 1}],
        }, content_type='application/json')

    def test_prices_only_after_approval_and_frozen(self, _):
        token = self.send().json()['token']
        public = self.client.get(f'/api/solicitudes/publica/{token}/').json()
        self.assertEqual([i['unit_price'] for i in public['items']], [None, None])
        self.assertIsNone(public['total'])
        # No part numbers on the customer's link, not even inside a name.
        self.assertEqual([(i['code'], i['name']) for i in public['items']], [(None, 'PEZONERA'), (None, 'JUNTA')])

        req = QuoteRequest.objects.get(token=token)
        self.client.force_login(self.seller)
        self.assertEqual(self.client.post(f'/api/solicitudes/{req.pk}/aprobar/').status_code, 403)
        self.client.force_login(self.manager)
        self.client.post(f'/api/solicitudes/{req.pk}/aprobar/', {'valid_days': 10}, content_type='application/json')

        CATALOG[0]['price'] = 999.0  # a later price change doesn't touch the quote
        try:
            self.client.logout()
            public = self.client.get(f'/api/solicitudes/publica/{token}/').json()
        finally:
            CATALOG[0]['price'] = 100.0
        self.assertEqual(public['status'], 'APPROVED')
        self.assertEqual([i['unit_price'] for i in public['items']], [100.0, None])  # B: se cotiza aparte
        self.assertEqual(public['total'], 200.0)

    def test_staff_adjust_before_approving_and_public_cannot_list(self, _):
        token = self.send().json()['token']
        req = QuoteRequest.objects.get(token=token)
        self.assertEqual(self.client.get('/api/solicitudes/').status_code, 403)
        self.client.force_login(self.seller)
        self.client.put(f'/api/solicitudes/{req.pk}/', {'items': [{'code': 'A', 'quantity': 5}, {'code': 'B', 'quantity': 0}]},
                        content_type='application/json')
        self.assertEqual([(i.producto_codigo, i.quantity) for i in req.items.all()], [('A', Decimal('5.00'))])

    def test_staff_price_is_kept_at_approval_and_hidden_until_then(self, _):
        req = quotes.create_request({'name': 'C', 'phone': '33 1234 5678', 'items': [{'key': '1', 'quantity': 2}, {'key': '2', 'quantity': 1}]})
        quotes.set_items(req, [{'code': 'B', 'quantity': 3, 'unit_price': '1500.50'}])
        row = {r['code']: r for r in quotes.staff_view(req)['items']}
        self.assertEqual((row['B']['unit_price'], row['B']['subtotal']), (Decimal('1500.50'), Decimal('4501.50')))
        self.assertEqual(row['A']['unit_price'], Decimal('100'))  # untouched: the catalog's
        self.assertIsNone(quotes.public_view(req)['total'])
        self.assertTrue(all(r['unit_price'] is None for r in quotes.public_view(req)['items']))
        quotes.approve(req, User.objects.create_user('jefa'))
        public = {r['code'] or r['name']: r for r in quotes.public_view(req)['items']}
        self.assertEqual(public['JUNTA']['unit_price'], Decimal('1500.50'))
        self.assertEqual(quotes.public_view(req)['total'], Decimal('4701.50'))

    def test_a_blank_price_goes_back_to_the_catalog_and_bad_ones_are_refused(self, _):
        req = quotes.create_request({'name': 'C', 'phone': '33 1234 5678', 'items': [{'key': '1', 'quantity': 1}]})
        quotes.set_items(req, [{'code': 'A', 'quantity': 1, 'unit_price': 90}])
        self.assertEqual(quotes.staff_view(req)['items'][0]['unit_price'], Decimal('90'))
        quotes.set_items(req, [{'code': 'A', 'quantity': 1, 'unit_price': ''}])
        self.assertEqual(quotes.staff_view(req)['items'][0]['unit_price'], Decimal('100'))
        for bad in ('abc', 0, -5):
            with self.assertRaises(quotes.QuoteError):
                quotes.set_items(req, [{'code': 'A', 'quantity': 1, 'unit_price': bad}])

    def test_pending_count_for_the_menu_badge(self, _):
        first = QuoteRequest.objects.get(token=self.send().json()['token'])
        self.send()
        self.assertEqual(self.client.get('/api/solicitudes/pendientes/').status_code, 403)
        self.client.force_login(self.seller)
        self.assertEqual(self.client.get('/api/solicitudes/pendientes/').json(), {'nuevas': 2})
        self.client.force_login(self.manager)
        self.client.post(f'/api/solicitudes/{first.pk}/rechazar/')
        self.assertEqual(self.client.get('/api/solicitudes/pendientes/').json(), {'nuevas': 1})

    def test_rejects_unknown_products_and_missing_phone(self, _):
        bad = self.client.post('/api/solicitudes/', {'name': 'X', 'phone': '33 1234 5678', 'items': [{'key': '9', 'quantity': 1}]},
                               content_type='application/json')
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.client.post('/api/solicitudes/', {'name': 'X', 'items': [{'key': '1', 'quantity': 1}]},
                                          content_type='application/json').status_code, 400)
        self.assertFalse(QuoteRequest.objects.exists())

    def test_public_form_is_rate_limited(self, _):
        codes = [self.send().status_code for _ in range(11)]
        self.assertEqual(codes[:10], [201] * 10)
        self.assertEqual(codes[10], 429)


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class PhotoUploadTests(TestCase):
    databases = {'default'}

    def setUp(self):
        import tempfile
        from pathlib import Path
        self.dir = Path(tempfile.mkdtemp())
        patcher = patch('catalog.services.PRODUCTS_DIR', self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        catalog = patch('api.views._catalog', return_value=[{'key': '7', 'CCODIGOPRODUCTO': 'A'}])
        catalog.start()
        self.addCleanup(catalog.stop)

    def photo(self):
        import io
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (300, 600), 'red').save(buf, 'JPEG')  # a photo: cropped
        return SimpleUploadedFile('IMG_0001.jpg', buf.getvalue(), content_type='image/jpeg')

    def test_staff_upload_becomes_a_square_webp_with_a_random_name(self):
        from PIL import Image
        from catalog.models import ProductImage
        self.assertEqual(self.client.post('/api/inventory/7/fotos/', {'foto': self.photo()}).status_code, 403)
        self.client.force_login(User.objects.create_user('vendedor', password='x'))
        res = self.client.post('/api/inventory/7/fotos/', {'foto': self.photo()})
        self.assertEqual(res.status_code, 201)
        img = ProductImage.objects.get(producto_codigo='A')
        self.assertRegex(img.file, r'^[0-9a-f]{16}\.webp$')
        self.assertTrue(img.is_primary)
        self.assertEqual(Image.open(self.dir / img.file).size, (300, 300))
        bad = self.client.post('/api/inventory/7/fotos/', {'foto': SimpleUploadedFile('x.jpg', b'not an image')})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.client.delete(f'/api/inventory/7/fotos/{img.pk}/').status_code, 204)
        self.assertFalse((self.dir / img.file).exists())


class ToSquareTests(SimpleTestCase):
    def test_cutouts_are_padded_and_photos_cropped(self):
        from PIL import Image
        from catalog.services import to_square
        cutout = Image.new('RGBA', (200, 100), (0, 0, 0, 0))
        cutout.paste((0, 0, 0, 255), (50, 25, 150, 75))
        padded = to_square(cutout)
        self.assertEqual((padded.size, padded.getpixel((0, 0))), ((200, 200), (255, 255, 255)))
        photo = to_square(Image.new('RGBA', (200, 100), (128, 128, 128, 255)))
        self.assertEqual(photo.size, (100, 100))

    def test_transparency_in_a_cropped_cutout_turns_white_not_black(self):
        from PIL import Image
        from catalog.services import to_square
        # The product fills the top corners, so it's cropped, but the bottom is transparent.
        cutout = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
        cutout.paste((40, 40, 40, 255), (0, 0, 100, 50))
        self.assertEqual(to_square(cutout).getpixel((50, 90)), (255, 255, 255))


# In-memory cache: rule changes must not touch the dev Redis.
@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class CatalogRulesTests(TestCase):
    """The seeded rules drive the public catalog; only Gerencia can change them."""
    databases = {'default'}

    @classmethod
    def setUpTestData(cls):
        cls.boss = User.objects.create_user('boss', password='x')
        cls.boss.profile.role = Profile.ROLE_MANAGEMENT
        cls.boss.profile.save()
        cls.seller = User.objects.create_user('seller', password='x')

    def setUp(self):
        repo = 'api.services.InventoryRepository.'
        erp = {'CIDPRODUCTO': 7, 'CCODIGOPRODUCTO': 'X', 'CNOMBREPRODUCTO': 'BOMBA', 'CPRECIO1': 100.0,
               'CIMPUESTO1': 16.0, 'CIDVALORCLASIFICACION1': 1, 'CIDVALORCLASIFICACION2': 2, 'CTIPOPRODUCTO': 1}
        for target, value in ((f'{repo}fetch_brand_names', {1: 'ACME'}), (f'{repo}fetch_stock', {7: 3.0}),
                              (f'{repo}fetch_units_sold', {}), ('api.services._gea_products', {})):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        # A fresh row each time: the catalog consumes the ERP's columns.
        patcher = patch(f'{repo}fetch_inventory', side_effect=lambda: [dict(erp)])
        patcher.start()
        self.addCleanup(patcher.stop)
        cache.clear()
        self.client.force_login(self.boss)

    def public(self):
        return {p['key']: p for p in get_inventory_catalog(False)}

    def test_special_order_product_is_public_on_order_and_quoted(self):
        SpecialOrderProduct.objects.create(pk=1, code='ESPECIAL-1', name='MAXGRIP ESPECIAL')
        cache.clear()
        mat = self.public()['900001']
        self.assertEqual((mat['CNOMBREPRODUCTO'], mat['on_order'], mat['price'], mat['brand']),
                         ('MAXGRIP ESPECIAL', True, 0, 'North West Rubber'))
        self.assertTrue(mat['special_order'])
        self.assertIsNone(mat['variant'])  # Slatted MaxGrip must not join the MaxGrip family
        self.assertEqual(self.public()['7']['price'], 116.0)

    def test_special_order_can_be_added_renamed_and_hidden(self):
        response = self.client.post('/api/catalogo/ajustes/especiales/', {'name': ' tapete nuevo '}, 'application/json')
        self.assertEqual(response.status_code, 200)
        new = response.json()['specials'][-1]
        pk = SpecialOrderProduct.objects.get().pk
        key = str(900000 + pk)
        self.assertEqual((new['key'], new['name']), (key, 'TAPETE NUEVO'))
        self.assertEqual(SpecialOrderProduct.objects.get().code, f'ESPECIAL-{pk}')
        self.client.patch(f'/api/catalogo/ajustes/especiales/{key}/', {'name': 'otro'}, 'application/json')
        self.assertEqual(self.public()[key]['CNOMBREPRODUCTO'], 'OTRO')
        self.client.put(f'/api/catalogo/ajustes/ocultos/{key}/', {'hidden': True}, 'application/json')
        self.assertNotIn(key, self.public())
        self.assertIn(key, {p['key'] for p in _catalog(True)})  # quotes still resolve it

    def test_an_erp_product_can_be_hidden_and_shown(self):
        self.client.put('/api/catalogo/ajustes/ocultos/7/', {'hidden': True}, 'application/json')
        self.assertNotIn('7', self.public())
        self.assertEqual([h['name'] for h in self.client.get('/api/catalogo/ajustes/').json()['hidden'] if h['key'] == '7'],
                         ['BOMBA'])
        self.client.put('/api/catalogo/ajustes/ocultos/7/', {'hidden': False}, 'application/json')
        self.assertIn('7', self.public())

    def test_hiding_something_unknown_is_refused(self):
        response = self.client.put('/api/catalogo/ajustes/ocultos/12345/', {'hidden': True}, 'application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(HiddenProduct.objects.filter(product_id=12345).exists())

    def test_category_rule_changes_what_the_public_sees(self):
        url = '/api/catalogo/ajustes/categorias/R/'
        self.client.put(url, {'show_price': False, 'on_order': 'NEVER', 'hide_brand': False}, 'application/json')
        self.assertIsNone(self.public()['7']['price'])
        self.assertEqual(self.client.put(url, {'show_price': 'si', 'on_order': 'X', 'hide_brand': False},
                                         'application/json').status_code, 400)

    def test_brand_shows_only_with_a_public_name(self):
        self.assertIsNone(self.public()['7']['brand'])
        url = '/api/catalogo/ajustes/marcas/'
        self.client.put(url, {'erp_name': 'ACME', 'public_name': 'Acme'}, 'application/json')
        self.assertEqual(self.public()['7']['brand'], 'Acme')
        self.client.put(url, {'erp_name': 'ACME', 'public_name': ''}, 'application/json')
        self.assertIsNone(self.public()['7']['brand'])

    def test_only_management_can_change_rules(self):
        self.client.force_login(self.seller)
        self.assertEqual(self.client.get('/api/catalogo/ajustes/').status_code, 403)
        self.assertEqual(self.client.put('/api/catalogo/ajustes/ocultos/7/', {'hidden': True},
                                         'application/json').status_code, 403)


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class ProductLineTests(TestCase):
    """Lines come from 'Línea:' in descriptions; a mat page recommends other lines, not its own versions."""
    databases = {'default'}

    def setUp(self):
        def row(key, name, price, stock, rank=None):
            return {'key': key, 'slug': name.lower(), 'CCODIGOPRODUCTO': f'C{key}', 'CNOMBREPRODUCTO': name, 'price': price,
                    'CPRECIO1': price, 'price_visible': True, 'in_stock': stock, 'on_order': not stock, 'sold_rank': rank, 'images': [], 'category': 'R_NW',
                    'line': 'CONFORT ANIMAL', 'variant': None}
        self.catalog = [row('1', 'PEBBLE A', 900.0, True, 2), row('2', 'PEBBLE B', 700.0, False), row('3', 'PEBBLE C', 800.0, True, 1),
                        row('4', 'IRON', 0.0, True), row('5', 'CLAVO', 20.0, True)]
        for code, text in (('C1', 'Línea: PebbleTop\nUso: pasillos.'), ('C2', 'Línea: PebbleTop\nDónde se usa: caballerizas.'),
                           ('C3', 'Línea: PebbleTop'), ('C4', 'Línea: IronGrip'), ('C5', 'Sin línea.')):
            ProductDescription.objects.create(producto_codigo=code, text=text)

    def test_groups_a_line_on_its_best_seller_in_stock_with_lowest_price_and_all_uses(self):
        rows = {r['line']: r for r in _lines(self.catalog)}
        self.assertEqual(sorted(rows), ['IronGrip', 'PebbleTop'])  # the nail has no line
        pebble = rows['PebbleTop']
        self.assertEqual((pebble['key'], pebble['price_from'], pebble['versions']), ('3', 700.0, 3))
        self.assertEqual(pebble['uses'], 'pasillos. caballerizas.')
        self.assertIsNone(rows['IronGrip']['price_from'])  # no price yet: quoted

    def test_the_area_estimate_price_ignores_narrow_and_calf_versions(self):
        self.catalog[1]['variant'] = {'options': {'Animal': 'Vacas', 'Ancho': '1 pie'}}  # the $700 one
        self.catalog[2]['variant'] = {'options': {'Animal': 'Becerras', 'Ancho': '4 pies'}}
        self.catalog[0]['variant'] = {'options': {'Animal': 'Vacas', 'Ancho': '4 pies'}}
        pebble = next(r for r in _lines(self.catalog) if r['line'] == 'PebbleTop')
        self.assertEqual((pebble['price_from'], pebble['mat_price']), (700.0, 900.0))

    def test_a_line_page_recommends_the_other_lines_and_others_stay_as_they_were(self):
        with patch('api.services._catalog', return_value=self.catalog), patch('api.services._gea_products', return_value={}), \
                patch('api.services.InventoryRepository.fetch_product_activity', return_value=None):
            detail = get_product_detail('1', False)
            nail = get_product_detail('5', False)
        self.assertEqual([r['line'] for r in detail['related_lines']], ['IronGrip'])
        self.assertEqual(detail['related'], [])
        self.assertEqual(nail['related_lines'], [])
        self.assertTrue(nail['related'])

    def test_people_mats_and_animal_mats_never_recommend_each_other(self):
        ProductDescription.objects.filter(producto_codigo='C5').update(text='Línea: StepSoft\nDónde se usa: operadores en fosas.')
        with patch('api.services._catalog', return_value=self.catalog), patch('api.services._gea_products', return_value={}), \
                patch('api.services.InventoryRepository.fetch_product_activity', return_value=None):
            pebble = get_product_detail('1', False)
            step = get_product_detail('5', False)
        self.assertEqual([r['line'] for r in pebble['related_lines']], ['IronGrip'])
        self.assertEqual(step['related_lines'], [])

    def test_lines_endpoint_is_public_and_hides_codes(self):
        with patch('api.services._catalog', return_value=self.catalog):
            response = self.client.get('/api/inventory/lineas/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('C1', str(response.content))

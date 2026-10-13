"""Quote requests. These use the local database only (databases = {'default'}),
so no test database is created on the ERP server; the ERP catalog is mocked."""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings

from accounts.models import Profile
from catalog.models import QuoteRequest

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

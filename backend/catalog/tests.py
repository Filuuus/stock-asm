"""Quote requests. These use the local database only (databases = {'default'}),
so no test database is created on the ERP server; the ERP catalog is mocked."""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from accounts.models import Profile
from catalog.models import QuoteRequest

CATALOG = [
    {'CCODIGOPRODUCTO': 'A', 'CNOMBREPRODUCTO': 'PEZONERA', 'CPRECIO1': 100.0, 'stock': 5.0,
     'in_stock': True, 'images': []},
    {'CCODIGOPRODUCTO': 'B', 'CNOMBREPRODUCTO': 'JUNTA', 'CPRECIO1': 0.0, 'stock': 0.0,
     'in_stock': False, 'images': []},
]


def catalog(is_worker):
    # The public never gets prices from the catalog.
    return [{**p, 'CPRECIO1': p['CPRECIO1'] if is_worker else None} for p in CATALOG]


# In-memory cache: the form's rate limit must not count against the dev Redis.
@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
@patch('catalog.quotes.get_inventory_catalog', side_effect=catalog)
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
            'items': [{'code': 'A', 'quantity': 2}, {'code': 'B', 'quantity': 1}],
        }, content_type='application/json')

    def test_prices_only_after_approval_and_frozen(self, _):
        token = self.send().json()['token']
        public = self.client.get(f'/api/solicitudes/publica/{token}/').json()
        self.assertEqual([i['unit_price'] for i in public['items']], [None, None])
        self.assertIsNone(public['total'])

        req = QuoteRequest.objects.get(token=token)
        self.client.force_login(self.seller)
        self.assertEqual(self.client.post(f'/api/solicitudes/{req.pk}/aprobar/').status_code, 403)
        self.client.force_login(self.manager)
        self.client.post(f'/api/solicitudes/{req.pk}/aprobar/', {'valid_days': 10}, content_type='application/json')

        CATALOG[0]['CPRECIO1'] = 999.0  # a later price change doesn't touch the quote
        try:
            self.client.logout()
            public = self.client.get(f'/api/solicitudes/publica/{token}/').json()
        finally:
            CATALOG[0]['CPRECIO1'] = 100.0
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
        bad = self.client.post('/api/solicitudes/', {'name': 'X', 'phone': '33 1234 5678', 'items': [{'code': 'Z', 'quantity': 1}]},
                               content_type='application/json')
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.client.post('/api/solicitudes/', {'name': 'X', 'items': [{'code': 'A', 'quantity': 1}]},
                                          content_type='application/json').status_code, 400)
        self.assertFalse(QuoteRequest.objects.exists())

    def test_public_form_is_rate_limited(self, _):
        codes = [self.send().status_code for _ in range(11)]
        self.assertEqual(codes[:10], [201] * 10)
        self.assertEqual(codes[10], 429)

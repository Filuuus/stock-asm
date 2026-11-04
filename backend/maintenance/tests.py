"""The plan's logic on made-up data (SimpleTestCase), and the visit/order endpoints on the local test database
(the ERP-backed plan is mocked)."""

from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from accounts.models import Profile

from .models import OrderLine, Parlor, PartChange, Visit
from .services import (
    add_months,
    base_code,
    counter_monthly,
    cross_client_months,
    due_rows,
    gea_rule,
    interval,
    merge_purchases,
    order_proposal,
    propose_visits,
    shortages,
    was_there,
)

TODAY = date(2026, 11, 3)
LINER = '7021-2725-230'


def parlor(id=1, client='103-1', hours=4, parts=((LINER, 32),)):
    return {'id': id, 'client': client, 'hours_per_day': hours, 'parts': list(parts)}


class PurchaseTests(SimpleTestCase):
    def test_base_code_drops_gea_suffix_only(self):
        self.assertEqual(base_code(' 7021-2764-010w '), '7021-2764-010')
        self.assertEqual(base_code('6306'), '6306')

    def test_purchases_within_45_days_are_one_change(self):
        merged = merge_purchases([('c', LINER, date(2026, 1, 1), 16), ('c', LINER, date(2026, 2, 10), 16),
                                  ('c', LINER, date(2026, 7, 1), 32), ('c', LINER, date(2026, 8, 1), -4)])
        self.assertEqual(merged[('c', LINER)], [[date(2026, 1, 1), 32], [date(2026, 7, 1), 32]])

    def test_cross_client_needs_three_clients_and_skips_long_gaps(self):
        def buys(client, *days):
            return [(client, LINER, d, 32) for d in days]
        lines = (buys('a', date(2020, 1, 1), date(2020, 7, 1), date(2024, 1, 1))  # 3.5-year gap ignored
                 + buys('b', date(2021, 1, 1), date(2021, 9, 1)) + buys('c', date(2022, 1, 1), date(2023, 1, 1)))
        months = cross_client_months(merge_purchases(lines))[LINER]
        self.assertAlmostEqual(months, 8.0, delta=0.2)
        self.assertNotIn(LINER, cross_client_months(merge_purchases(lines[:5])))


class IntervalTests(SimpleTestCase):
    def test_gea_rule_takes_the_replacement_rule(self):
        service = {'rules': [{'hours': 1500, 'months': 12, 'action': 'Verificar fisuras'},
                             {'hours': 750, 'months': 6, 'action': 'reemplazar'}]}
        self.assertEqual(gea_rule(service), (750, 6))
        self.assertIsNone(gea_rule({'rules': [{'hours': 1500, 'months': 12, 'action': 'limpiar'}]}))

    def test_gea_hours_become_months_with_the_parlors_milking_hours(self):
        self.assertAlmostEqual(interval((750, 6), 7, None, None, 'gea')[0], 3.5, delta=0.1)
        self.assertEqual(interval((750, 6), 2, None, None, 'gea'), (6, 'GEA'))  # the months come first
        self.assertEqual(interval((750, 6), None, None, None, 'gea'), (6, 'GEA'))

    def test_policy_order(self):
        self.assertEqual(interval((750, 6), 4, 9.0, 10.0, 'gea'), (6, 'GEA'))
        self.assertEqual(interval((750, 6), 4, 9.0, 10.0, 'actual'), (9.0, 'cliente'))
        self.assertEqual(interval(None, 4, None, 10.0, 'gea'), (10.0, 'clientes'))
        self.assertEqual(interval((750, 6), 4, None, None, 'actual'), (6, 'GEA'))
        self.assertEqual(interval(None, 4, None, None, 'gea'), (None, None))


class DueTests(SimpleTestCase):
    def rows(self, purchases, confirmed=None, today=TODAY):
        return due_rows([parlor()], merge_purchases(purchases), confirmed or {}, {LINER: (750, 6)}, {}, today, 'gea')

    def test_last_full_change_sets_the_due_date(self):
        [row] = self.rows([('103-1', LINER, date(2026, 6, 1), 32), ('103-1', LINER, date(2026, 9, 1), 4)])
        self.assertEqual(row['last_change'], date(2026, 6, 1))  # 4 liners is a top-up, not a change
        self.assertEqual(row['due'], date(2026, 11, 30))  # 6 months of 30.44 days
        self.assertEqual(row['status'], 'ok')

    def test_a_confirmed_change_counts_like_an_invoice(self):
        [row] = self.rows([('103-1', LINER, date(2026, 1, 1), 32)], {(1, LINER): date(2026, 10, 1)})
        self.assertEqual(row['last_change'], date(2026, 10, 1))

    def test_statuses(self):
        self.assertEqual(self.rows([('103-1', LINER, date(2026, 1, 1), 32)])[0]['status'], 'overdue')
        self.assertEqual(self.rows([('103-1', LINER, date(2022, 1, 1), 32)])[0]['status'], 'stale')
        self.assertEqual(self.rows([])[0]['status'], 'unknown')


def row(code, qty, due, status='ok', parlor=1):
    return {'parlor': parlor, 'code': code, 'quantity': qty, 'due': due, 'status': status}


class PlanTests(SimpleTestCase):
    def test_visits_take_parts_due_by_month_end_not_stale_not_already_open(self):
        rows = [row(LINER, 32, date(2027, 1, 20)), row('A', 1, date(2026, 10, 1), 'overdue'),
                row('B', 1, date(2027, 2, 1)), row('C', 1, date(2020, 1, 1), 'stale'), row('D', 1, date(2026, 12, 1))]
        self.assertEqual(propose_visits(rows, date(2027, 1, 1), {(1, 'D')}), {1: [(LINER, 32), ('A', 1)]})

    def test_order_covers_until_the_next_order_lands_plus_counter_buffer(self):
        rows = [row(LINER, 32, date(2026, 12, 15)), row(LINER, 20, date(2026, 12, 20), parlor=2),
                row(LINER, 40, date(2027, 1, 5), parlor=3)]  # after the next order lands
        [line] = order_proposal(rows, date(2026, 11, 1), {LINER: 10}, {LINER: 5}, {LINER: 2.4})
        self.assertEqual(line, {'code': LINER, 'services': 52, 'buffer': 5, 'stock': 10, 'on_order': 5, 'order': 42})

    def test_nothing_to_order_when_stock_covers_it(self):
        self.assertEqual(order_proposal([row(LINER, 8, date(2026, 12, 1))], date(2026, 11, 1), {LINER: 20}, {}, {}), [])

    def test_negative_stock_counts_as_none(self):
        [line] = order_proposal([row(LINER, 8, date(2026, 12, 1))], date(2026, 11, 1), {LINER: -3}, {}, {})
        self.assertEqual(line['order'], 8)

    def test_counter_sales_leave_out_registered_parlors_and_old_sales(self):
        lines = [('x', LINER, date(2026, 5, 1), 24), ('103-1', LINER, date(2026, 5, 1), 32),
                 ('x', LINER, date(2025, 1, 1), 100)]
        self.assertEqual(counter_monthly(lines, {'103-1'}, TODAY), {LINER: 2})

    def test_shortages_for_visits_in_the_next_30_days(self):
        visits = [{'status': 'scheduled', 'date': date(2026, 11, 20), 'month': date(2026, 11, 1),
                   'parts': [{'code': LINER, 'quantity': 32}]},
                  {'status': 'proposed', 'date': None, 'month': date(2027, 1, 1), 'parts': [{'code': 'A', 'quantity': 1}]},
                  {'status': 'done', 'date': date(2026, 11, 2), 'month': date(2026, 11, 1),
                   'parts': [{'code': 'B', 'quantity': 1}]}]
        self.assertEqual(shortages(visits, {LINER: 20}, TODAY), {LINER: 12})

    def test_gps_stop_near_the_place(self):
        place = (20.8170, -102.7620)
        stops = [(date(2026, 11, 2), (20.8180, -102.7620)), (date(2026, 11, 3), (20.83, -102.76))]  # 110 m, 1.4 km
        self.assertEqual(was_there(stops, [place]), [date(2026, 11, 2)])

    def test_add_months(self):
        self.assertEqual(add_months(date(2026, 11, 1), 2), date(2027, 1, 1))


class EndpointTests(TestCase):
    def setUp(self):
        self.parlor = Parlor.objects.create(client_code='103-1', stalls=8)
        self.visit = Visit.objects.create(parlor=self.parlor, month=date(2027, 1, 1),
                                          parts=[{'code': LINER, 'quantity': 32}, {'code': 'A', 'quantity': 1}])

    def login(self, role):
        user = get_user_model().objects.create_user(username=role, password='x')
        user.profile.role = role  # the profile is created with the user
        user.profile.save()
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_done_records_the_changed_parts_and_redo_replaces_them(self):
        client = self.login(Profile.ROLE_SALESPERSON)
        url = f'/api/servicios/visitas/{self.visit.id}/'
        self.assertEqual(client.patch(url, {'status': 'done'}, format='json').status_code, 400)  # needs a date
        client.patch(url, {'date': '2026-12-10', 'status': 'done', 'parts': [LINER]}, format='json')
        self.assertEqual(list(PartChange.objects.values_list('code', 'date')), [(LINER, date(2026, 12, 10))])
        client.patch(url, {'status': 'done'}, format='json')
        self.assertEqual(PartChange.objects.count(), 2)
        client.patch(url, {'status': 'scheduled'}, format='json')
        self.assertEqual(PartChange.objects.count(), 0)

    def test_orders_are_for_purchasing_and_management(self):
        self.assertEqual(self.login(Profile.ROLE_SALESPERSON).get('/api/servicios/pedidos/').status_code, 403)
        client = self.login(Profile.ROLE_PURCHASING)
        res = client.post('/api/servicios/pedidos/', {'lines': [{'code': LINER, 'quantity': 64}]}, format='json')
        self.assertEqual(res.status_code, 201)
        line = OrderLine.objects.get()
        client.patch(f'/api/servicios/pedidos/{line.id}/', {'received': True}, format='json')
        self.assertEqual(client.get('/api/servicios/pedidos/').json(), [])

    @patch('maintenance.views.build_plan', return_value={'alerts': []})
    def test_plan_needs_login(self, _):
        self.assertEqual(APIClient().get('/api/servicios/plan/').status_code, 403)
        self.assertEqual(self.login(Profile.ROLE_SALESPERSON).get('/api/servicios/plan/').status_code, 200)

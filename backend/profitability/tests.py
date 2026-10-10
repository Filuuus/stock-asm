"""Tests for the profitability pure functions, on made-up data."""

from datetime import datetime

from django.test import SimpleTestCase, TestCase

from .vehicle_reports import parse_fuel, parse_maintenance
from .services import (
    allocate_credit_notes, allocate_route_costs, allocate_supplier_discounts, build_facts, is_advance_application,
    product_info, route_costs,
)
from .weights import DEFAULT_KG, estimate_kg


class EstimateKgTests(SimpleTestCase):
    gea = {'7751-0040-505': {'kg': '215.105', 'unit': 'PZA'}, '7750-0220-528': {'kg': '65.83', 'unit': 'PZA'}}

    def test_sources_in_order(self):
        self.assertEqual(estimate_kg('BIO-SLC2', 'SANOLAC LILA 25 KG', 1699, self.gea), (25.0, 'nombre'))
        self.assertEqual(estimate_kg('7751-0040-505L', 'LUXTEK 5 LTS', 677, self.gea), (5.0, 'nombre'))
        self.assertEqual(estimate_kg('7751-0040-505', 'LUXTEK SELLADOR 55 GAL', 21429, self.gea), (215.105, 'GEA'))
        self.assertEqual(estimate_kg('X', 'CUALQUIER COSA', 10, self.gea, 'KILOGRAMO'), (1.0, 'unidad'))
        self.assertEqual(estimate_kg('117997', 'VENTILADOR 72" ECVD', 57118, self.gea), (100.0, 'estimado'))

    def test_guards_against_capacities_and_packs(self):
        self.assertEqual(estimate_kg('R02', 'REGULADOR DE VACIO 3500 LTS', 1573, self.gea), (DEFAULT_KG, 'estimado'))
        # $2.7/kg means the GEA weight is the whole roll, not the meter sold.
        self.assertEqual(estimate_kg('7750-0220-528W', 'MANGUERA DE LECHE (ROLLO)', 177, self.gea), (0.15, 'estimado'))
        self.assertEqual(estimate_kg('ACETURV', 'ACEITE TURBINA', 77, self.gea, 'LITRO'), (0.87, 'estimado'))


class AllocateCreditNotesTests(SimpleTestCase):
    # Invoice 10: two lines, 300 + 100. Invoice 20: one line, 500.
    lines = [[10, 1, 7, 100, 300.0], [10, 1, 7, 101, 100.0], [20, 2, 8, 102, 500.0]]

    def test_spreads_by_applied_amount_then_line_net(self):
        # Net 100 (116 with IVA): 58 applied to invoice 10, 58 to invoice 20.
        notes = [[1, 2026, 3, 9, 7, 100.0, 116.0, 10, 58.0], [1, 2026, 3, 9, 7, 100.0, 116.0, 20, 58.0]]
        rows = {r[4]: round(r[5], 2) for r in allocate_credit_notes(notes, self.lines)}
        self.assertEqual(rows, {100: -37.5, 101: -12.5, 102: -50.0})

    def test_unapplied_part_stays_on_the_note_without_product(self):
        notes = [[1, 2026, 3, 9, 7, 100.0, 116.0, 10, 29.0], [2, 2026, 4, 9, 8, 50.0, 58.0, None, None]]
        rows = [(r[1], r[2], r[4], round(r[5], 2)) for r in allocate_credit_notes(notes, self.lines)]
        self.assertEqual(rows, [(3, 1, 100, -18.75), (3, 1, 101, -6.25), (3, 9, None, -75.0), (4, 9, None, -50.0)])


class BuildFactsTests(SimpleTestCase):
    def test_nets_returns_credits_and_commissions_into_one_row(self):
        sales = [
            [4, 2026, 3, 1, 7, 100, 10, 1000.0, 800.0],
            [5, 2026, 3, 1, 7, 100, 2, 200.0, 160.0],  # return: takes its commission back too
        ]
        credits = [(2026, 3, 1, 7, 100, -50.0)]  # no commission on credit notes
        paid = [('2026-03', 'Z1', 7, 100, 12.5), ('2026-04', 'Z1', 7, 100, 3.0)]  # paid month, not invoice month
        facts = build_facts(sales, credits, paid, lambda agent, client: f'Z{agent}', lambda product: 25.0,
                            lambda zone, client, product: 0.02)
        self.assertEqual(facts, [
            ['2026-03', 'Z1', 7, 100, 8.0, 750.0, 640.0, 200.0, 16.0, 12.5, 0.0, 0.0, 0.0],
            ['2026-04', 'Z1', 7, 100, 0.0, 0.0, 0.0, 0.0, 0.0, 3.0, 0.0, 0.0, 0.0],
        ])


class SupplierDiscountTests(SimpleTestCase):
    def test_spreads_each_month_over_its_products_cost(self):
        row = lambda month, product, cost: [month, 'Z1', 7, product, 0, 0, cost, 0, 0, 0, 0.0, 0.0, 0.0]
        facts = [row('2026-03', 1, 300.0), row('2026-03', 1, 100.0), row('2026-03', 2, 500.0), row('2026-04', 1, 50.0)]
        allocate_supplier_discounts(facts, {'2026-03': 40.0}, lambda product: product == 1)
        self.assertEqual([f[10] for f in facts], [30.0, 10.0, 0.0, 0.0])


class ProductInfoTests(SimpleTestCase):
    def test_manual_weight_wins_and_services_weigh_nothing(self):
        products = [
            [1, 'BIO-1', 'SANOLAC 25 KG', 1, 50, 0, 'PIEZA'],
            [2, 'SRV', 'MANO DE OBRA', 3, 0, 0, ''],
        ]
        brands = {50: 'BIONAT-SANO, SA DE CV', 0: '(Ninguna)'}
        info = product_info(products, brands, {1: 1700}, {1: 24.5}, {})
        self.assertEqual((info[1]['kg'], info[1]['source'], info[1]['category']), (24.5, 'manual', 'B'))
        self.assertEqual((info[2]['kg'], info[2]['source'], info[2]['brand']), (0.0, 'servicio', 'Sin marca'))


class AdvanceApplicationTests(SimpleTestCase):
    def test_by_word_or_by_an_advance_invoice_folio(self):
        advances = {17367, 19411}
        self.assertTrue(is_advance_application('F 19456 APLICACION DE ANTICIPO DE LA F-19411 A LA F-19456', advances))
        self.assertTrue(is_advance_application('F 18153 DE LA F-17367  APLICA F-18153', advances))
        self.assertFalse(is_advance_application('B 18272 CLIENTE TUVO PROBLEMAS DE CALIDAD\r\nAPLICA F-B18272', advances))
        self.assertFalse(is_advance_application('F 20000 DE LA F-17368 APLICA F-20000', advances))  # not an advance
        self.assertFalse(is_advance_application(None, advances))


class RouteCostTests(SimpleTestCase):
    def test_pools_by_component(self):
        vehicles = [
            {'pool': 'ZONA1', 'sheet_name': 'HILUX1', 'maintenance_account': '511', 'uses_lp': True, 'gps_imei': 'a',
             'km_per_liter': 0, 'price_per_liter': 0, 'annual_insurance': 1200.0},
            {'pool': 'ZONA2', 'sheet_name': 'HILUX2', 'maintenance_account': '', 'uses_lp': False, 'gps_imei': 'b',
             'km_per_liter': 8.0, 'price_per_liter': 20.0, 'annual_insurance': 0.0},
        ]
        costs = route_costs(
            ['2026-09', '2026-10'], {1: 'ZONA1', 2: 'ZONA2'}, vehicles, [('ALMACEN', 'Renta', 25000.0)],
            {('2026-10', 1): 9000.0, ('2026-10', 2): 8000.0},
            {('2026-09', '511'): 777.0, ('2026-10', '511'): 500.0, ('2026-10', '500503021'): 3000.0},
            {('2026-10', 'a'): 999.0, ('2026-10', 'b'): 400.0},  # LP truck ignores its km
            # September is in the workbook: its figures replace the ledger and GPS for the vehicles it names.
            {('2026-09', 'HILUX1', 'fuel'): 4000.0, ('2026-09', 'HILUX1', 'maintenance'): 250.0},
        )
        self.assertEqual(costs, {
            '2026-09': {
                'ZONA1': {'Seguros': 100.0, 'Combustible': 4000.0, 'Mantenimiento': 250.0},
                'ALMACEN': {'Renta': 25000.0},
            },
            '2026-10': {
                'ZONA1': {'Sueldos': 9000.0, 'Mantenimiento': 500.0, 'Seguros': 100.0, 'Combustible': 3000.0},
                'ZONA2': {'Sueldos': 8000.0, 'Combustible': 1000.0},
                'ALMACEN': {'Renta': 25000.0},
            },
        })

    def test_route_by_own_kg_warehouse_by_all_kg_services_by_sales(self):
        row = lambda zone, product, units, net, kg: ['2026-10', zone, 7, product, units, net, 0, kg, 0, 0, 0.0, 0.0, 0.0]
        facts = [row('ZONA1', 1, 1, 1000.0, 75.0), row('ZONA2', 1, 1, 1000.0, 25.0), row('SERVICIOS', 9, 2, 400.0, 0.0)]
        costs = {'2026-10': {'ZONA1': {'x': 300.0}, 'ALMACEN': {'x': 100.0}, 'SERVICIOS': {'x': 40.0},
                             'ZONA2': {'x': 10.0}}, '2026-11': {'ZONA1': {'x': 5.0}}}
        unallocated = allocate_route_costs(facts, costs, lambda product: product == 9)
        self.assertEqual([f[11] for f in facts], [375.0, 35.0, 40.0])
        self.assertEqual(unallocated, {'2026-11': {'ZONA1': 5.0}})
        allocate_route_costs(facts, costs, lambda product: product == 9, by='pieces')  # services aren't pieces
        self.assertEqual([f[12] for f in facts], [350.0, 60.0, 40.0])


class VehicleReportTests(SimpleTestCase):
    def test_fuel_reads_each_month_total_by_its_own_header(self):
        rows = [
            ('ENERO 2026',), (None, 'JUAN JOSE', 'RAUL'), (None, 'HILUX 1', 'ALMACEN'),
            ('SEMANA 01', 10, 5), ('TOTAL SEMANAL', 10, 5), ('TOTAL ', 100.5, 7),
            ('FEBRERO 2026',), (None, 'F350', 'HILUX 1', 'ISUZU', 'ISUZU'), ('TOTAL', 3, None, 1311.49, 2970.48),
            ('NOVIEMBRE 2025',), (None, 'HILUX 1'), ('TOTAL', 999),  # last year's copied template
            ('MARZO 2026',), (None, 'HILUX 1'), ('TOTAL', 50),  # current month: half filled
        ]
        self.assertEqual(parse_fuel(rows, 2026, '2026-03'), {
            ('2026-01', 'HILUX1'): 100.5, ('2026-01', 'MONTACARGAS'): 7.0,
            ('2026-02', 'F350'): 3.0, ('2026-02', 'HILUX1'): 0.0, ('2026-02', 'ISUZU'): 4281.97,  # two Isuzus, added up
        })

    def test_maintenance_by_row_date(self):
        rows = [
            ('FEBRERO 2024',), ('FECHA', 'VEHICULO', 'PLACAS', 'CHOFER', 'PROVEEDOR', 'IMPORTE', 'CONCEPTO'),
            (datetime(2026, 2, 3), 'F 350', None, None, None, '2050', None),
            (datetime(2026, 2, 13), 'HILUX 1', None, None, None, '8534.48', None),
            (datetime(2026, 2, 18), 'HILUX 1', None, None, None, '1650', None),
            (datetime(2026, 2, 22), 'ISUZU', None, None, None, '68534.48', 'CARROSERIA'),  # the new truck's bed
            (datetime(2026, 2, 23), 'ISUZU', None, None, None, '500', 'REPARACION DE CARROCERIA'),
            (datetime(2025, 12, 18), 'MONTACARGAS', None, None, None, '2311.91', None),  # belongs to last year's file
            (None, None, None, None, 'TOTAL', '12234.48', None),
        ]
        self.assertEqual(parse_maintenance(rows, 2026, '2026-10'), {
            ('2026-02', 'F350'): 2050.0, ('2026-02', 'HILUX1'): 10184.48, ('2026-02', 'ISUZU'): 500.0,
        })


class SaveRouteSetupTests(TestCase):
    def test_replaces_rows_keeps_gps_units_and_rejects_bad_input_whole(self):
        from .models import PoolEmployee, PoolMonthlyCost, PoolVehicle
        from .setup import save_route_setup
        PoolEmployee.objects.all().delete()
        PoolMonthlyCost.objects.all().delete()
        PoolVehicle.objects.all().delete()
        truck = PoolVehicle.objects.create(name='Hilux', pool='ZONA1', gps_imei='123')
        PoolVehicle.objects.create(name='Vieja', pool='ZONA2')
        save_route_setup({
            'employees': [{'employee_id': 7, 'pool': 'ZONA1'}],
            'vehicles': [{'id': truck.id, 'name': 'Hilux 1', 'pool': 'ZONA2', 'sheet_name': 'hilux 1', 'annual_insurance': '1200'}],
            'monthly_costs': [{'label': 'Renta', 'pool': 'ALMACEN', 'monthly_amount': 25000}],
        })
        truck.refresh_from_db()
        self.assertEqual((truck.name, truck.pool, truck.sheet_name, truck.gps_imei), ('Hilux 1', 'ZONA2', 'HILUX1', '123'))
        self.assertEqual(PoolVehicle.objects.count(), 1)
        with self.assertRaises(ValueError):
            save_route_setup({'employees': [], 'vehicles': [], 'monthly_costs': [{'label': 'X', 'pool': 'ALMACEN',
                                                                                    'monthly_amount': -1}]})
        self.assertEqual(list(PoolEmployee.objects.values_list('employee_id', flat=True)), [7])
        self.assertEqual(PoolVehicle.objects.count(), 1)

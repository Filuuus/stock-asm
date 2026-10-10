"""Tests for the profitability pure functions, on made-up data."""

from django.test import SimpleTestCase

from .services import allocate_credit_notes, build_facts, product_info
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
    def test_nets_returns_and_credits_into_one_row_with_kg(self):
        sales = [
            [4, 2026, 3, 1, 7, 100, 10, 1000.0, 800.0],
            [5, 2026, 3, 1, 7, 100, 2, 200.0, 160.0],  # return
        ]
        credits = [(2026, 3, 1, 7, 100, -50.0)]
        facts = build_facts(sales, credits, lambda agent, client: f'Z{agent}', lambda product: 25.0)
        self.assertEqual(facts, [['2026-03', 'Z1', 7, 100, 8.0, 750.0, 640.0, 200.0]])


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

from django.test import SimpleTestCase

from .services import expense_category, summarize, summarize_results


class SummarizeTests(SimpleTestCase):
    def test_returns_net_and_ytd_windows(self):
        rows = [
            (2026, 8, 4, 1, 10, 1000.0, 600.0),   # ZONA1 sale, brand 10
            (2026, 8, 5, 1, 10, 200.0, 120.0),    # return against it
            (2026, 8, 7, 2, None, 50.0, 0.0),     # credit note, ZONA2, no brand
            (2025, 8, 4, 2, 10, 400.0, 100.0),    # last year, inside YTD window
            (2025, 11, 4, 2, 10, 999.0, 0.0),     # last year, after August: not YTD
        ]
        r = summarize(rows, 2026, 8, {10: 'GEA'})
        aug = r['months'][-1]
        self.assertEqual(len(r['months']), 20)  # Jan 2025 .. Aug 2026
        self.assertEqual((aug['ventas'], aug['devoluciones'], aug['costo']), (750.0, 250.0, 480.0))
        self.assertEqual((aug['zonas']['ZONA1'], aug['zonas']['ZONA2']), (800.0, -50.0))
        self.assertEqual(r['brands'][0], {'brand': 'GEA', 'ytd': 800.0, 'ytd_prev': 400.0})
        self.assertEqual(r['brands'][1]['brand'], 'Sin marca')


class ResultsTests(SimpleTestCase):
    def test_expense_categories(self):
        self.assertEqual(expense_category('CUOTAS DE SEGURO, RETIRO, CESANTIA EN EDAD AV'), 'Nómina')
        self.assertEqual(expense_category('SEGUROS Y FIANZAS'), 'Seguros')
        self.assertEqual(expense_category('IGI'), 'Fletes e importación')
        self.assertEqual(expense_category('ARTICULOS DE VIGILANCIA Y SEGURIDAD'), 'Otros')
        self.assertEqual(expense_category('GAS LP'), 'Combustible')

    def test_operating_result(self):
        rows = [
            (2026, 8, '4001', 'VENTAS', -1000.0),
            (2026, 8, '4002', 'DESCUENTOS', 100.0),
            (2026, 8, '5001', 'COSTO DE VENTAS', 500.0),
            (2026, 8, '5005', 'SUELDOS Y SALARIOS POR VENTAS', 150.0),
            (2026, 8, '5007', 'GASTOS FINANCIEROS', 40.0),
            (2026, 9, '4001', 'VENTAS', -999.0),  # outside the keys
        ]
        [aug] = summarize_results(rows, ['2026-08'])
        self.assertEqual((aug['ingresos'], aug['costo'], aug['financieros']), (900.0, 500.0, 40.0))
        self.assertEqual(aug['gastos']['Nómina'], 150.0)
        self.assertEqual(aug['utilidad_operativa'], 250.0)

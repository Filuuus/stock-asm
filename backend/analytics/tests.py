from django.test import SimpleTestCase

from .services import expense_category, indicators, month_end_balances, summarize, summarize_results


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


class IndicatorTests(SimpleTestCase):
    def test_month_end_balances_include_year_end_periods(self):
        rows = [(2025, 12, '100102', 100.0), (2025, 13, '100102', 5.0), (2026, 1, '100102', 10.0)]
        b = month_end_balances(rows, ['2025-12', '2026-01'])
        self.assertEqual((b['2025-12']['100102'], b['2026-01']['100102']), (100.0, 115.0))

    def test_ratios_and_break_even(self):
        resultados = [{'month': '2026-01', 'ingresos': 1000.0, 'costo': 600.0, 'financieros': 10.0,
                       'utilidad_operativa': 200.0, 'gastos': {'Nómina': 200.0}}]
        balances = {'2026-01': {'100102': 50.0, '103103': 310.0, '100109': 600.0, '200101': -300.0}}
        [k] = indicators(resultados, balances)
        self.assertEqual(k['margen_operativo'], 0.2)
        self.assertEqual(k['razon_circulante'], round(960 / 300, 4))
        self.assertEqual(k['prueba_acida'], 1.2)
        self.assertEqual(k['dias_cxc'], 9.61)  # 310 / (1000 / 31 days)
        self.assertEqual(k['pe_operativo_ytd'], 500.0)  # 200 / 40% gross margin
        self.assertEqual(k['cobertura_pef'], round(1000 / 525, 4))

    def test_unposted_month(self):
        r = {'month': '2026-09', 'ingresos': 3.0, 'costo': 0.0, 'financieros': 0.0,
             'utilidad_operativa': 3.0, 'gastos': {'Nómina': 0.0}}
        self.assertEqual(indicators([r], {}), [{'month': '2026-09', 'posted': False}])

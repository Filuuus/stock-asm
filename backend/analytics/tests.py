from django.test import SimpleTestCase

from datetime import date, datetime

from .services import aging, chart_end_month, expense_accounts, expense_category, financial_accounts, indicators, month_end_balances, summarize, summarize_results


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
        self.assertEqual(r['brands'][0], {'brand': 'GEA', 'ytd': 800.0, 'ytd_prev': 400.0, 'mes': 800.0, 'mes_prev': 400.0})
        self.assertEqual(r['brands'][1]['brand'], 'Sin marca')

    def test_chart_runs_past_the_picked_month(self):
        rows = [(2026, 3, 4, 1, 10, 100.0, 0.0), (2026, 8, 4, 1, 10, 50.0, 0.0)]
        r = summarize(rows, 2026, 3, {10: 'GEA'}, end_month=9)
        self.assertEqual(r['months'][-1]['month'], '2026-09')
        self.assertEqual(r['brands'][0]['ytd'], 100.0)  # August isn't in a March YTD

    def test_chart_end_month(self):
        today = date(2026, 10, 3)  # September is the last complete month
        self.assertEqual(chart_end_month(2025, 4, today), 12)
        self.assertEqual(chart_end_month(2026, 4, today), 9)
        self.assertEqual(chart_end_month(2026, 10, today), 10)  # current month, picked on purpose
        self.assertEqual(chart_end_month(2027, 1, date(2027, 1, 15)), 1)  # last complete month is Dec 2026


class ResultsTests(SimpleTestCase):
    def test_expense_categories(self):
        cases = [
            ('500501009', 'CUOTAS DE SEGURO, RETIRO, CESANTIA EN ED', 'Nómina'),
            ('500503010', 'SEGUROS Y FIANZAS', 'Seguros'),
            ('500508002', 'IGI', 'Fletes e importación'),
            ('500508005', 'COSTO INDIRECTO', 'Fletes e importación'),  # by code: port and customs costs
            ('500511099', 'MANTENIMIENTO VEHICULO NUEVO', 'Vehículos y combustible'),  # any new vehicle account
            ('500503021', 'GAS LP', 'Vehículos y combustible'),
            ('500515003', 'REPARACIONES Y FABRICACIONES', 'Materiales y reparaciones'),
            ('500602003', 'HONORARIOS A PERSONAS MORALES', 'Honorarios y publicidad'),
            ('500603005', 'ENERGIA ELECTRICA', 'Mantenimiento y servicios'),
            ('500503006', 'ARTICULOS DE VIGILANCIA Y SEGURIDAD', 'Otros'),
            ('500615000', 'GASTOS NO DEDUCIBLES', 'Otros'),  # 5006 15 is not 5005 15
            ('500616001', 'ARRENDAMIENTO DE VEHICULO', 'Vehículos y combustible'),  # vehicle leases
        ]
        for code, name, expected in cases:
            self.assertEqual(expense_category(code, name), expected, name)

    def test_expense_accounts(self):
        rows = [
            (2026, 8, '500502003', 'HONORARIOS A PERSONAS MORALES', 100.0),  # selling branch
            (2026, 8, '500602003', 'HONORARIOS A PERSONAS  MORALES', 50.0),  # admin branch, same expense
            (2025, 8, '500602003', 'HONORARIOS A PERSONAS MORALES', 40.0),
            (2025, 8, '500603005', 'ENERGIA ELECTRICA', 9.0),  # only last year: still listed
            (2026, 8, '400101001', 'VENTAS', -999.0),  # not an expense
            (2026, 7, '500603005', 'ENERGIA ELECTRICA', 7.0),  # another month
        ]
        r = expense_accounts(rows, '2026-08', '2025-08')
        self.assertEqual(r['Honorarios y publicidad'],
                         [{'cuenta': 'HONORARIOS A PERSONAS MORALES', 'monto': 150.0, 'anterior': 40.0}])
        self.assertEqual(r['Mantenimiento y servicios'], [{'cuenta': 'ENERGIA ELECTRICA', 'monto': 0.0, 'anterior': 9.0}])
        self.assertEqual(set(r), {'Honorarios y publicidad', 'Mantenimiento y servicios'})

    def test_financial_accounts(self):
        rows = [
            (2026, 8, '500701000', 'PERDIDA CAMBIARIA', 270.0),
            (2026, 8, '400401000', 'UTILIDAD CAMBIARIA', -20.0),  # a gain: negative, listed last
            (2025, 8, '500701000', 'PERDIDA CAMBIARIA', 8.0),
            (2026, 8, '500503010', 'SEGUROS Y FIANZAS', 99.0),  # operating expense, not financial
        ]
        self.assertEqual(financial_accounts(rows, '2026-08', '2025-08'), [
            {'cuenta': 'PERDIDA CAMBIARIA', 'monto': 270.0, 'anterior': 8.0},
            {'cuenta': 'UTILIDAD CAMBIARIA', 'monto': -20.0, 'anterior': 0.0},
        ])
        self.assertEqual(financial_accounts([], '2026-08', '2025-08'), [])

    def test_operating_result(self):
        rows = [
            (2026, 8, '400101001', 'VENTAS', -1000.0),
            (2026, 8, '400201001', 'DESCUENTOS', 100.0),
            (2026, 8, '500101001', 'COSTO DE VENTAS', 500.0),
            (2026, 8, '500501001', 'SUELDOS Y SALARIOS POR VENTAS', 150.0),
            (2026, 8, '500701001', 'GASTOS FINANCIEROS', 40.0),
            (2026, 9, '400101001', 'VENTAS', -999.0),  # outside the keys
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


class AgingTests(SimpleTestCase):
    def test_buckets_by_days_past_due_and_ranks_overdue_clients(self):
        def f(client, due, pending, doc_type=4):
            return {'CIDDOCUMENTODE': doc_type, 'CIDCLIENTEPROVEEDOR': client, 'CRAZONSOCIAL': f'C{client}', 'CFECHA': datetime(2026, 1, 1),
                    'CFECHAVENCIMIENTO': datetime.fromisoformat(due), 'CPENDIENTE': pending}
        rows = [f(1, '2026-10-05', 100), f(1, '2026-10-04', 10), f(2, '2026-09-05', 20), f(2, '2026-09-04', 30),
                f(3, '2026-07-07', 40), f(3, '2026-07-06', 50)]
        result = aging(rows, date(2026, 10, 5))
        self.assertEqual([(b['bucket'], b['pendiente'], b['documentos']) for b in result['antiguedad']], [
            ('Por vencer', 100, 1), ('1-30 días', 30, 2), ('31-60 días', 30, 1),
            ('61-90 días', 40, 1), ('Más de 90 días', 50, 1)])
        self.assertEqual(result['pendiente'], 250)
        self.assertEqual([(c['client_id'], c['vencido'], c['dias_vencido']) for c in result['clientes']],
                         [(3, 90, 91), (2, 50, 31), (1, 10, 1)])
        self.assertEqual(result['clientes'][2]['pendiente'], 110)

    def test_credits_pay_the_clients_oldest_charges_first(self):
        def f(client, due, pending, doc_type=4):
            return {'CIDDOCUMENTODE': doc_type, 'CIDCLIENTEPROVEEDOR': client, 'CRAZONSOCIAL': f'C{client}',
                    'CFECHA': datetime(2018, 1, 1), 'CFECHAVENCIMIENTO': datetime.fromisoformat(due),
                    'CPENDIENTE': pending}
        rows = [
            f(1, '2018-04-01', 25, doc_type=13), f(1, '2026-09-01', 100), f(1, '2026-10-20', 50),
            f(1, '2019-01-01', 25, doc_type=9), f(1, '2026-01-01', 40, doc_type=7),  # 65: the 13, then 40 of 100
            f(2, '2026-09-01', 30), f(2, '2026-01-01', 45, doc_type=5),  # covered, 15 left over
            f(3, '2021-03-05', 260, doc_type=5),  # credit with nothing open
        ]
        result = aging(rows, date(2026, 10, 5))
        self.assertEqual([(b['bucket'], b['pendiente'], b['documentos']) for b in result['antiguedad']], [
            ('Por vencer', 50, 1), ('1-30 días', 0, 0), ('31-60 días', 60, 1), ('61-90 días', 0, 0),
            ('Más de 90 días', 0, 0)])
        self.assertEqual(result['pendiente'], 110)
        self.assertEqual(result['saldo_a_favor'], 275)
        self.assertEqual([(c['client_id'], c['vencido'], c['pendiente']) for c in result['clientes']], [(1, 60, 110)])

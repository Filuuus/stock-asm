"""The plan's logic on made-up data (SimpleTestCase), and the endpoints on the local test database (the
ERP-backed plan is mocked)."""

from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from accounts.models import Profile

from .services import (
    add_months,
    apply_swaps,
    model_swaps,
    swap_options,
    same_part_other_model,
    base_code,
    counter_monthly,
    cross_client_months,
    due_rows,
    expand_kits,
    infer_parlors,
    parlor_product,
    service_items,
    gea_rule,
    interval,
    kit_contents,
    part_events,
    relevance,
    alias_family,
    alias_same_product,
    category,
    family_mates,
    kit_family,
    merge_purchases,
    one_per_family,
    part_family,
    product_key,
    same_products,
    what_they_buy,
    order_day,
    order_proposal,
)

TODAY = date(2026, 11, 3)
LINER = '7021-2725-230'


def parlor(id=1, client='103-1', hours=4, parts=((LINER, 32),)):
    return {'id': id, 'client': client, 'hours_per_day': hours, 'parts': [(code, qty, 'Colectores') for code, qty in parts]}


class PurchaseTests(SimpleTestCase):
    def test_base_code_drops_gea_suffix_only(self):
        self.assertEqual(base_code(' 7021-2764-010w '), '7021-2764-010')
        self.assertEqual(base_code('6306'), '6306')

    def test_purchases_within_45_days_are_one_change(self):
        merged = merge_purchases([('c', LINER, date(2026, 1, 1), 16), ('c', LINER, date(2026, 2, 10), 16),
                                  ('c', LINER, date(2026, 7, 1), 32), ('c', LINER, date(2026, 8, 1), -4)])
        self.assertEqual(merged[('c', LINER)], [[date(2026, 1, 1), 32, None], [date(2026, 7, 1), 32, None]])

    def test_the_merge_window_does_not_slide(self):
        # Every 40 days: the third purchase is 80 days after the first, so it starts a change of its own.
        merged = merge_purchases([('c', LINER, date(2025, 9, 11), 10), ('c', LINER, date(2025, 10, 21), 50),
                                  ('c', LINER, date(2025, 11, 30), 20)])
        self.assertEqual([e[0] for e in merged[('c', LINER)]], [date(2025, 9, 11), date(2025, 11, 30)])

    def test_a_change_keeps_its_first_invoice(self):
        merged = merge_purchases([('c', LINER, date(2026, 1, 1), 16, 501), ('c', LINER, date(2026, 1, 20), 16, 502)])
        self.assertEqual(merged[('c', LINER)], [[date(2026, 1, 1), 32, 501]])

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
        self.assertAlmostEqual(interval((750, 6), 7, None, None)[0], 3.5, delta=0.1)
        self.assertEqual(interval((750, 6), 2, None, None), (6, 'GEA'))  # the months come first
        self.assertEqual(interval((750, 6), None, None, None), (6, 'GEA'))

    def test_without_gea_the_clients_rhythm_then_others_then_the_calendar(self):
        self.assertEqual(interval((750, 6), 4, 9.0, 10.0), (6, 'GEA'))
        self.assertEqual(interval(None, 4, 9.0, 10.0), (9.0, 'cliente'))
        self.assertEqual(interval(None, 4, None, 10.0, sheet=24), (10.0, 'clientes'))
        self.assertEqual(interval(None, 4, None, None, sheet=24), (24, 'calendario'))
        self.assertEqual(interval(None, 4, None, None), (None, None))


class EventTests(SimpleTestCase):
    start, end = date(2025, 1, 1), date(2027, 12, 31)

    def test_done_missed_and_due(self):
        # Every 6 months: Jan 2025 done; due Jul 2025, changed in Sep (missed in Jul, done in Sep); due Mar 2026.
        events = part_events([date(2025, 1, 10), date(2025, 9, 5)], 6, TODAY, self.start, self.end)
        self.assertEqual(events, [(date(2025, 1, 10), 'done'), (date(2025, 7, 11), 'missed'), (date(2025, 9, 5), 'done'),
                                  (date(2026, 3, 6), 'missed')])

    def test_an_up_to_date_part_repeats_its_interval(self):
        events = part_events([date(2026, 8, 3)], 6, TODAY, self.start, self.end)
        self.assertEqual([k for _, k in events], ['done', 'due', 'due'])  # Feb and Aug 2027
        self.assertEqual(events[1][0], date(2027, 2, 1))

    def test_changed_on_time_is_not_missed(self):
        events = part_events([date(2025, 1, 10), date(2025, 7, 20)], 6, TODAY, self.start, self.end)
        self.assertNotIn('missed', [k for d, k in events if d < date(2026, 1, 1)])


class DueTests(SimpleTestCase):
    def rows(self, purchases, today=TODAY):
        return due_rows([parlor()], merge_purchases(purchases), {LINER: (750, 6)}, {}, today)

    def test_last_full_change_sets_the_due_date(self):
        [row] = self.rows([('103-1', LINER, date(2026, 6, 1), 32), ('103-1', LINER, date(2026, 9, 1), 4)])
        self.assertEqual(row['last_change'], date(2026, 6, 1))  # 4 liners is a top-up, not a change
        self.assertEqual(row['due'], date(2026, 11, 30))  # 6 months of 30.44 days
        self.assertEqual(row['status'], 'ok')

    def test_statuses(self):
        self.assertEqual(self.rows([('103-1', LINER, date(2026, 1, 1), 32)])[0]['status'], 'overdue')
        self.assertEqual(self.rows([('103-1', LINER, date(2022, 1, 1), 32)])[0]['status'], 'stale')
        # Last bought over 2 years ago: bought elsewhere, even if barely overdue; a 24-month part gets 30 months.
        long_part = [parlor(parts=(('M', 1),))]
        rows = lambda day: due_rows(long_part, merge_purchases([('103-1', 'M', day, 1)]), {'M': (4500, 24)}, {}, TODAY)
        self.assertEqual(rows(date(2024, 10, 1))[0]['status'], 'overdue')
        self.assertEqual(rows(date(2024, 4, 1))[0]['status'], 'stale')
        self.assertEqual(self.rows([('103-1', LINER, date(2024, 10, 1), 32)])[0]['status'], 'stale')  # 6-month liner
        self.assertEqual(self.rows([])[0]['status'], 'unknown')
        no_rule = due_rows([parlor()], merge_purchases([('103-1', LINER, date(2026, 1, 1), 32)]), {}, {}, TODAY)
        self.assertEqual(no_rule[0]['status'], 'no_interval')


class LaborTests(SimpleTestCase):
    def kinds(self, labor):
        [row] = due_rows([parlor()], merge_purchases([('103-1', LINER, date(2026, 6, 1), 32, 7)]), {LINER: (750, 6)},
                         {}, TODAY, labor)
        return [e['kind'] for e in row['events'] if e['date'] == date(2026, 6, 1)]

    def test_an_invoice_without_our_labor_was_installed_by_someone_else(self):
        self.assertEqual(self.kinds(None), ['done'])
        self.assertEqual(self.kinds({'103-1': [date(2026, 6, 20)]}), ['done'])  # labor billed 19 days later
        self.assertEqual(self.kinds({'103-1': [date(2026, 8, 1)]}), ['external'])
        self.assertEqual(self.kinds({}), ['external'])


class InferTests(SimpleTestCase):
    LINERS = {LINER, '7020-2725-211'}

    def infer(self, lines, labor, registry=None):
        return infer_parlors(merge_purchases(lines), labor, self.LINERS, registry or {},
                             lambda code, codes: False, TODAY)

    def test_service_items_need_our_labor_or_a_steady_rhythm(self):
        once = [[date(2026, 3, 1), 48, 1]]
        self.assertEqual(service_items(once, [date(2026, 3, 5)], True, TODAY), once)
        self.assertEqual(service_items(once, [], True, TODAY), [])  # a single counter sale
        self.assertEqual(service_items([[date(2026, 3, 1), 4, 1]], [date(2026, 3, 1)], True, TODAY), [])  # top-up
        self.assertEqual(service_items([[date(2023, 3, 1), 48, 1]], [date(2023, 3, 1)], True, TODAY), [])  # stale
        steady = [[date(2025, 3, 1), 1, 1], [date(2025, 9, 1), 1, 2], [date(2026, 3, 1), 1, 3]]
        self.assertEqual(service_items(steady, [], False, TODAY), steady)

    def test_liners_and_labor_make_a_parlor(self):
        found = self.infer([('103-9', '7020-2725-211', date(2026, 3, 1), 48), ('103-9', 'P', date(2026, 3, 1), 1),
                            ('103-8', '7020-2725-211', date(2026, 3, 1), 48)], {'103-9': [date(2026, 3, 2)]})
        self.assertEqual(found['new'], {'103-9': {'stalls': 12, 'parts': {'7020-2725-211': 48, 'P': 1}}})

    def test_one_liner_per_parlor_the_latest(self):
        found = self.infer([('103-9', LINER, date(2026, 1, 1), 32), ('103-9', '7020-2725-211', date(2026, 7, 1), 34)],
                           {'103-9': [date(2026, 1, 1), date(2026, 7, 1)]})
        self.assertEqual(found['new']['103-9'], {'stalls': 8, 'parts': {'7020-2725-211': 32}})

    def test_existing_parlor_gets_missing_parts_and_consistent_stalls(self):
        registry = {'103-9': [{'id': 5, 'active': True, 'stalls': 12, 'codes': {LINER}, 'dismissed': {'Q'}}]}
        lines = [('103-9', LINER, date(2026, 1, 1), 40), ('103-9', LINER, date(2026, 7, 1), 40),
                 ('103-9', 'P', date(2026, 7, 1), 2), ('103-9', 'Q', date(2026, 7, 1), 2)]
        found = self.infer(lines, {'103-9': [date(2026, 7, 1)]}, registry)
        self.assertEqual(found['add'], [(5, 'P', 2)])  # Q was removed by staff
        self.assertEqual(found['stalls'], [(5, 12, 10)])
        # One change isn't enough to overrule the calendar.
        self.assertEqual(self.infer(lines[1:], {'103-9': [date(2026, 7, 1)]}, registry)['stalls'], [])


class ParlorProductTests(SimpleTestCase):
    def test_only_the_parlors_service_counts(self):
        gea = {'P': {'path': ['- Conventional Milkin...', 'Pulsado']}, 'S': {'path': ['Higiene', 'Selladores']},
               'F': {'path': ['- Barn Equipment -']}, 'M': {'path': ['- Farm Management', 'Sensores']}}
        self.assertTrue(parlor_product('P', 'PULSADOR', gea, set()))
        self.assertTrue(parlor_product('M', 'MEDIDOR', gea, set()))
        self.assertTrue(parlor_product('204JD', 'PEZONERA SUSTITUTO', gea, set()))
        self.assertTrue(parlor_product('C300-11', 'BOLA DE CIERRE', gea, {'C300-11'}))
        self.assertFalse(parlor_product('S', 'SELLADOR', gea, set()))
        self.assertFalse(parlor_product('F', 'VENTILADOR', gea, set()))
        self.assertFalse(parlor_product('BIO-SLC2', 'SANOLAC', gea, set()))


def row(code, qty, due, status='ok', parlor=1):
    return {'parlor': parlor, 'code': code, 'quantity': qty, 'due': due, 'status': status}


class FamilyTests(SimpleTestCase):
    def test_families_from_gea_category_else_erp_name(self):
        self.assertEqual(part_family('7026-2725-211', 'PEZONERA GOMA IQ-GQ-R GLOBAL', {}), 'pezonera')
        hose = {'path': ['- Liners & Milk tubes', 'Tubos de leche largos...'], 'desc': 'Manga de leche Transp 0.625in'}
        self.assertEqual(part_family('7750-0220-528', 'MANGUERA DE LECHE TRANSPARENTE', hose), 'manguera de leche')
        # The ERP calls it a long milk tube; GEA says it's a short one: its own family.
        short = {'path': ['Tubos de leche de gom...'], 'desc': 'Tubo corto de leche 10x4x160 Rub'}
        self.assertEqual(part_family('7021-7101-030', 'TUBO LARGO DE LECHE 10 X 4 X 160', short), '7021-7101-030')

    def test_one_per_family_keeps_the_latest_invoiced_within_a_group(self):
        families = {'old': 'pezonera', 'new': 'pezonera', 'hose': 'manguera de leche', 'wash': 'manguera de leche'}
        parts = [('Colectores', 'old', 320), ('Colectores', 'new', 320), ('Colectores', 'hose', 20),
                 ('Lavado', 'wash', 10)]
        kept, dropped = one_per_family(parts, families, {'old': date(2023, 9, 1), 'new': date(2026, 8, 3)})
        self.assertEqual(dropped, [('Colectores', 'old', 320)])
        self.assertIn(('Lavado', 'wash', 10), kept)  # a hose somewhere else is another job
        kept, dropped = one_per_family(parts[:2], families, {})
        self.assertEqual(dropped, [('Colectores', 'new', 320)])  # nothing invoiced: the first listed


class KitTests(SimpleTestCase):
    gea = {'7051-9905-000': {'desc': 'Juego de servicio - Pulsation (C) StimoPuls/AutoPuls Apex'},
           '7051-9905-010': {'desc': 'Juego de servicio - Pulsation (P) StimoPuls/AutoPuls Apex'},
           '7161-9905-020': {'desc': 'Kit de servicio - Manejo de la leche (C) Apex Control Valve'},
           '7023-2638-000': {'desc': 'Tubo corto de vacío 7x3x220'}}

    def test_complete_and_partial_kits_of_one_unit_are_one_family(self):
        self.assertEqual(kit_family(self.gea['7051-9905-000']['desc']), kit_family(self.gea['7051-9905-010']['desc']))
        self.assertEqual(part_family('7051-9905-000', '', self.gea['7051-9905-000']),
                         part_family('7051-9905-010', '', self.gea['7051-9905-010']))
        self.assertIsNone(kit_family(self.gea['7023-2638-000']['desc']))
        families = {c: part_family(c, '', e) for c, e in self.gea.items()}
        self.assertEqual(family_mates(['7051-9905-010', '7161-9905-020'], families), {'7051-9905-010': ['7051-9905-000']})

    def test_liner_family_is_the_liner_not_what_goes_with_it(self):
        self.assertEqual(part_family('a', 'PEZONERA GOMA GQ-R GLOBAL', {}), 'pezonera')
        self.assertEqual(part_family('b', '', {'desc': 'ClassicLiner - Goma pezonera 27/23/58'}), 'pezonera')
        self.assertEqual(part_family('c', 'CASQUILLO PORTA PEZONERA GLOBAL', {}), 'c')
        self.assertEqual(part_family('d', 'MANGUERA DE VACIO SIMPLE 9/32"', {'path': ['Tubos de vacío largos']}), 'd')

    def test_a_mates_invoice_counts_for_the_registered_part_of_that_client_only(self):
        families = {'010': 'kit', '000': 'kit', 'h527': 'hose', 'h528': 'hose', 'wash': 'hose'}
        mates = family_mates(['010', 'h527'], families)
        lines = [('103-1', '000', date(2026, 8, 3), 80, 9), ('103-2', '000', date(2026, 8, 3), 12, 10),
                 ('103-1', 'h528', date(2026, 9, 1), 20, 11)]
        one_hose = [parlor(client='103-1', parts=(('010', 80), ('h527', 20)))]
        self.assertEqual(alias_family(lines, one_hose, families, mates),
                         [('103-1', '010', date(2026, 8, 3), 80, 9), ('103-2', '000', date(2026, 8, 3), 12, 10),
                          ('103-1', 'h527', date(2026, 9, 1), 20, 11)])
        two_hoses = [parlor(client='103-1', parts=(('h527', 20), ('wash', 10)))]
        self.assertEqual(alias_family(lines, two_hoses, families, mates)[2][1], 'h528')  # can't tell which


class RelevanceTests(SimpleTestCase):
    def test_on_time_parts_keep_their_value_skipped_ones_sink(self):
        on_time = [(date(2024, 6, 1), 'done'), (date(2025, 6, 1), 'done'), (date(2026, 6, 1), 'done')]
        skipped = [(date(2024, 6, 1), 'done'), (date(2025, 6, 1), 'missed'), (date(2026, 6, 1), 'missed')]
        self.assertEqual(relevance(on_time, 9000, TODAY), {'per_year': 1.0, 'on_time': 1.0, 'score': 9000})
        self.assertEqual(relevance(skipped, 9000, TODAY)['score'], 3000)
        self.assertEqual(relevance([(date(2020, 1, 1), 'done')], 100, TODAY), {'per_year': 0.0, 'on_time': None, 'score': 50})


class CategoryTests(SimpleTestCase):
    def test_one_name_per_group(self):
        self.assertEqual(category('JUEGOS DE ORDEÑO'), 'Colectores')
        self.assertEqual(category('  Bomba de leche (pendiente de uso) '), 'Bomba de leche')
        self.assertEqual(category('RECIBO DE LECHE'), 'Recibidor de leche')
        self.assertEqual(category('ALGO NUEVO'), 'Algo nuevo')
        self.assertEqual(category(None), 'Otras')


class SameProductTests(SimpleTestCase):
    names = {'7009-2786-020': 'BOLA DE CIERRE COLECTOR CLASSIC 300', 'C300-11': 'BOLA DE CIERRE COLECTOR CLASSIC 300 SUST',
             '527': 'MANGUERA DE LECHE TRANSPARENTE 5/8"', '528': 'MANGUERA DE LECHE TRANSPARENTE 5/8" (ROLLO)',
             'X': 'JUNTA ANULAR 16 X 2'}

    def test_one_product_under_two_codes(self):
        self.assertEqual(product_key('Manguera de leche transparente 5/8" (rollo)'), 'MANGUERADELECHETRANSPARENTE58')
        self.assertEqual(product_key('MILSAN SUSTITUTO DE LECHE 25 KG'), 'MILSANSUSTITUTODELECHE25KG')
        self.assertEqual(same_products(['7009-2786-020', '527', 'X'], self.names),
                         {'7009-2786-020': ['C300-11'], '527': ['528']})

    def test_its_invoices_count_for_the_registered_code_even_with_other_family_parts(self):
        lines = [('103-1', 'C300-11', date(2026, 4, 23), 8, 7, 900.0), ('103-2', 'C300-11', date(2026, 4, 23), 8, 8, 900.0)]
        parlors = [parlor(client='103-1', parts=(('7009-2786-020', 8),))]
        aliased = alias_same_product(lines, parlors, {'7009-2786-020': ['C300-11']})
        self.assertEqual([l[1] for l in aliased], ['7009-2786-020', 'C300-11'])


class KitContentsTests(SimpleTestCase):
    def test_buying_the_assembly_changes_the_parts_inside(self):
        gea = {'SWITCH': {'parts': [{'code': 'FLOAT', 'qty': 1}], 'spare_parts': [{'code': 'OTHER'}]},
               'FLOAT': {'parts': []}}
        contents = kit_contents({'FLOAT'}, gea)
        self.assertEqual(contents, {'SWITCH': ['FLOAT']})
        lines = [('103-1', 'SWITCH', date(2026, 4, 28), 1, 5, 2000.0), ('103-2', 'SWITCH', date(2026, 4, 28), 1, 6, 2000.0)]
        parlors = [parlor(client='103-1', parts=(('FLOAT', 1),))]
        self.assertEqual(expand_kits(lines, parlors, contents)[2:], [('103-1', 'FLOAT', date(2026, 4, 28), 1, 5, 0.0)])


class WhatTheyBuyTests(SimpleTestCase):
    families = {'listed': 'pezonera', 'bought': 'pezonera', 'tried': 'pezonera', 'hose': 'manguera de leche',
                'hose2': 'manguera de leche'}

    def test_a_liner_follows_the_liner_the_client_changed_to(self):
        purchases = {'bought': [[date(2026, 6, 9), 48]], 'tried': [[date(2026, 10, 1), 4]], 'hose2': [[date(2026, 1, 1), 20]]}
        parts, swaps = what_they_buy([('C', 'listed', 48), ('C', 'hose', 20)], self.families, purchases)
        self.assertEqual(parts, [('C', 'bought', 48), ('C', 'hose', 20)])  # 4 liners to try is not a change;
        self.assertEqual(swaps, [('listed', 'bought')])                     # hoses are never swapped

    def test_keeps_the_listed_liner_when_it_is_the_latest_change(self):
        purchases = {'listed': [[date(2026, 6, 9), 48]], 'bought': [[date(2024, 1, 1), 48]]}
        self.assertEqual(what_they_buy([('C', 'listed', 48)], self.families, purchases), ([('C', 'listed', 48)], []))


class PlanTests(SimpleTestCase):
    def test_order_covers_until_the_next_order_lands_plus_counter_buffer(self):
        rows = [row(LINER, 32, date(2026, 12, 15)), row(LINER, 20, date(2026, 12, 20), parlor=2),
                row(LINER, 40, date(2027, 1, 5), parlor=3)]  # after the next order lands
        [line] = order_proposal(rows, date(2026, 11, 1), {LINER: 10}, {LINER: 2.4})
        self.assertEqual(line, {'code': LINER, 'services': 52, 'buffer': 5, 'stock': 10, 'order': 47})

    def test_nothing_to_order_when_stock_covers_it(self):
        self.assertEqual(order_proposal([row(LINER, 8, date(2026, 12, 1))], date(2026, 11, 1), {LINER: 20}, {}), [])

    def test_negative_stock_counts_as_none(self):
        [line] = order_proposal([row(LINER, 8, date(2026, 12, 1))], date(2026, 11, 1), {LINER: -3}, {})
        self.assertEqual(line['order'], 8)

    def test_counter_sales_leave_out_registered_parlors_and_old_sales(self):
        lines = [('x', LINER, date(2026, 5, 1), 24), ('103-1', LINER, date(2026, 5, 1), 32),
                 ('x', LINER, date(2025, 1, 1), 100)]
        self.assertEqual(counter_monthly(lines, {'103-1'}, TODAY), {LINER: 2})

    def test_order_day_is_the_first_wednesday_on_or_after_today(self):
        self.assertEqual(order_day(date(2026, 11, 3)), date(2026, 11, 4))
        self.assertEqual(order_day(date(2026, 11, 4)), date(2026, 11, 4))
        self.assertEqual(order_day(date(2026, 11, 5)), date(2026, 12, 2))
        self.assertEqual(order_day(date(2026, 12, 20)), date(2027, 1, 6))

    def test_add_months(self):
        self.assertEqual(add_months(date(2026, 11, 1), 2), date(2027, 1, 1))


class ModelSwapTests(SimpleTestCase):
    def test_another_model_of_the_same_part(self):
        same = same_part_other_model
        self.assertTrue(same('7049-1703-000', 'MEMBRANA VACUREX 5000 CPL', '7047-1703-000', 'MEMBRANA 1200 CPL VACUREX'))
        self.assertTrue(same('7161-9905-020', 'JGO SERVICIO GESTION DE LECHE VALVULA CONTROL APEX CPL',
                             '7161-9905-040', 'JGO SERVICIO GESTION DE LECHE VALVULA CONTROL'))
        self.assertTrue(same('4999-1070-173', 'COPA DE LAVADO 7360 1½" 51MM', '4999-1070-170', 'COPA DE LAVADO 7330 MELTEC'))

    def test_not_a_size_a_stray_word_or_the_same_product(self):
        same = same_part_other_model
        self.assertFalse(same('0007-2413-750', 'JUNTA ANULAR 16 X 2', '0007-2507-820', 'JUNTA ANULAR 16 X 3.5'))
        self.assertFalse(same('4999-1090-160', 'MANGUERA DE VACIO SIMPLE GOMA 9/16"', '4999-1090-016', 'MANGUERA DE VACIO SIMPLE 9/32"'))
        self.assertFalse(same('7049-2799-000', 'FILTRO DE AIRE VACUREX', '7051-2306-010', 'FILTRO AIRE 75 X 22 X 16 D7 CPL'))
        self.assertFalse(same('7750-0220-527', 'MANGUERA DE LECHE 5/8"', '7750-0220-528', 'MANGUERA DE LECHE 5/8" (ROLLO)'))

    def test_swaps_to_the_model_changed_to_last_and_moves_its_history(self):
        parlors = [{'id': 1, 'client': 'c', 'parts': [('OLD', 2, 'Vacío'), ('KEPT', 1, 'Vacío')],
                    'sheet_months': {('OLD', 'Vacío'): 12}}]
        purchases = {('c', 'OLD'): [[date(2023, 1, 1), 2, 1]], ('c', 'NEW'): [[date(2025, 1, 1), 2, 2]],
                     ('c', 'TOPUP'): [[date(2026, 1, 1), 0.5, 3]]}
        swaps = model_swaps(parlors, purchases, {(1, 'OLD'): ['NEW', 'TOPUP'], (1, 'KEPT'): ['OLD']})
        self.assertEqual(swaps, {(1, 'OLD'): 'NEW'})  # a top-up isn't a change; a registered part isn't a swap
        out, lines = apply_swaps(parlors, [('c', 'OLD', date(2023, 1, 1), 2), ('d', 'OLD', date(2023, 1, 1), 2)], swaps)
        self.assertEqual(out[0]['parts'], [('NEW', 2, 'Vacío'), ('KEPT', 1, 'Vacío')])
        self.assertEqual((out[0]['sheet_months'], out[0]['registered_as']), ({('NEW', 'Vacío'): 12}, {'NEW': 'OLD'}))
        self.assertEqual([l[1] for l in lines], ['NEW', 'OLD'])  # only that client's invoices move

    def test_a_part_in_two_places_takes_each_purchase_in_the_largest_place_it_covers(self):
        hose = '7021-7106-028'
        p = {'id': 1, 'client': 'c', 'hours_per_day': 4, 'parts': [(hose, 272, 'Colectores'), (hose, 56, 'LECC')]}
        purchases = merge_purchases([('c', hose, date(2025, 3, 1), 140), ('c', hose, date(2025, 10, 8), 200),
                                     ('c', hose, date(2026, 8, 3), 50)])
        rows = {r['group']: r for r in due_rows([p], purchases, {}, {}, TODAY)}
        changes = lambda g: [e['date'] for e in rows[g]['events'] if e['kind'] == 'done']  # noqa: E731
        # 140 m: the claws only; 200 m: all of it (over half of 328 m); 50 m: the LECC only.
        self.assertEqual(changes('Colectores'), [date(2025, 3, 1), date(2025, 10, 8)])
        self.assertEqual(changes('LECC'), [date(2025, 10, 8), date(2026, 8, 3)])

    def test_family_products_are_options_only_for_a_parlor_with_one_of_the_family(self):
        families = {'CLEAR': 'hose', 'GREEN': 'hose', 'RUBBER': 'hose', 'ROLL': 'hose', 'KIT-C': 'kit: x', 'KIT-P': 'kit: x'}
        mates = {'CLEAR': ['GREEN', 'ROLL', 'RUBBER'], 'RUBBER': ['CLEAR', 'GREEN', 'ROLL'], 'KIT-C': ['KIT-P']}
        same = {'CLEAR': ['ROLL']}
        one = {'id': 1, 'parts': [('CLEAR', 20, 'Colectores'), ('KIT-C', 8, 'Pulsadores')]}
        two = {'id': 2, 'parts': [('CLEAR', 20, 'Colectores'), ('RUBBER', 10, 'Lavado')]}
        options = swap_options([one, two], {'KIT-C': ['KIT-Z']}, mates, families, same)
        self.assertEqual(options, {(1, 'CLEAR'): ['GREEN', 'RUBBER'], (1, 'KIT-C'): ['KIT-Z']})


class EndpointTests(TestCase):
    def login(self, role):
        user = get_user_model().objects.create_user(username=role, password='x')
        user.profile.role = role  # the profile is created with the user
        user.profile.save()
        client = APIClient()
        client.force_authenticate(user)
        return client

    @patch('maintenance.views.build_plan', return_value={})
    def test_plan_needs_login(self, _):
        self.assertEqual(APIClient().get('/api/servicios/plan/').status_code, 403)
        self.assertEqual(self.login(Profile.ROLE_SALESPERSON).get('/api/servicios/plan/').status_code, 200)

    def test_a_clients_phone_is_kept_and_fixes_their_open_service_quotes(self):
        from catalog.models import QuoteRequest
        from .models import ClientPhone, Parlor, ServiceQuote
        parlor = Parlor.objects.create(client_code='103-1', stalls=8)
        req = QuoteRequest.objects.create(name='Cliente', phone='', from_staff=True)
        ServiceQuote.objects.create(parlor=parlor, request=req, places=[])
        client = self.login(Profile.ROLE_SALESPERSON)
        url = '/api/servicios/clientes/103-1/telefono/'
        self.assertEqual(client.put(url, {'phone': '123'}, format='json').status_code, 400)
        self.assertEqual(client.put('/api/servicios/clientes/999/telefono/', {'phone': '3312345678'}, format='json').status_code, 404)
        self.assertEqual(client.put(url, {'phone': '33 1234 5678'}, format='json').status_code, 200)
        self.assertEqual(ClientPhone.objects.get().phone, '33 1234 5678')
        req.refresh_from_db()
        self.assertEqual(req.phone, '33 1234 5678')

    def test_a_prospect_can_be_marked_contacted(self):
        from .models import Parlor
        parlor = Parlor.objects.create(client_code='103-1', stalls=8)
        client = self.login(Profile.ROLE_SALESPERSON)
        url = f'/api/servicios/salas/{parlor.pk}/contactado/'
        self.assertIsNotNone(client.post(url).json()['contacted_at'])
        self.assertIsNone(client.delete(url).json()['contacted_at'])

    @patch('maintenance.services.fetch_client_contact', return_value=('Cliente', '3330000000'))
    @patch('api.services._catalog', return_value=[{'key': '11', 'CCODIGOPRODUCTO': '7049-1703-000'}])
    def test_service_quote_becomes_a_request_owned_by_its_author(self, *_):
        from catalog.models import QuoteRequest
        from .models import Parlor
        parlor = Parlor.objects.create(client_code='103-1', stalls=8)
        client = self.login(Profile.ROLE_SALESPERSON)
        url = f'/api/servicios/salas/{parlor.pk}/cotizar/'
        self.assertEqual(client.post(url, {'items': []}, format='json').status_code, 400)
        # The same part in two places: the quote keeps the earlier due date.
        r = client.post(url, {'items': [{'key': '11', 'quantity': 2, 'code': '7049-1703-000', 'group': 'Regulador',
                                         'due': '2026-12-01'},
                                        {'key': '11', 'quantity': 0, 'code': '7049-1703-000', 'group': 'Otros',
                                         'due': '2026-01-21'}]},
                        format='json')
        self.assertEqual(r.status_code, 201)
        req = QuoteRequest.objects.get(pk=r.json()['id'])
        self.assertEqual((req.name, req.owner.username, req.items.get().producto_codigo, req.items.get().quantity),
                         ('Cliente', Profile.ROLE_SALESPERSON, '7049-1703-000', 2))
        self.assertEqual(req.service_quote.due, {'7049-1703-000': '2026-01-21'})
        from catalog.quotes import _rows
        self.assertEqual(_rows(req, {}, live_prices=False)[0]['due'], '2026-01-21')
        from .services import quoted_places
        self.assertEqual(quoted_places([parlor.pk])[(parlor.pk, '7049-1703-000', 'Regulador')][1],
                         {'id': req.pk, 'status': 'cotizado'})
        req.status = QuoteRequest.STATUS_REJECTED
        req.save()
        self.assertEqual(quoted_places([parlor.pk]), {})  # a closed quote no longer marks its parts

    def test_part_quantity_can_be_fixed_or_the_part_removed(self):
        from .models import Parlor, ParlorPart
        part = ParlorPart.objects.create(parlor=Parlor.objects.create(client_code='103-1', stalls=80),
                                         code='7021-7106-028', quantity=272, group='Colectores')
        client = self.login(Profile.ROLE_SALESPERSON)
        url = f'/api/servicios/piezas/{part.pk}/'
        self.assertEqual(client.patch(url, {'quantity': 0}, format='json').status_code, 400)
        self.assertEqual(client.patch(url, {'quantity': 50}, format='json').json()['quantity'], 50)
        self.assertEqual(client.delete(url).status_code, 204)
        self.assertFalse(ParlorPart.objects.exists())
        self.assertEqual(Parlor.objects.get().dismissed, ['7021-7106-028'])  # so the sync doesn't add it back

    def test_a_change_by_someone_else_restarts_the_interval_and_can_be_undone(self):
        from .models import ExternalChange, Parlor, ParlorPart
        part = ParlorPart.objects.create(parlor=Parlor.objects.create(client_code='103-1', stalls=8),
                                         code=LINER, quantity=32, group='Colectores')
        client = self.login(Profile.ROLE_SALESPERSON)
        self.assertEqual(client.post('/api/servicios/externos/', {'parts': [part.pk], 'day': '2099-01-01'},
                                     format='json').status_code, 400)
        r = client.post('/api/servicios/externos/', {'parts': [part.pk], 'day': '2026-10-01', 'note': 'otro taller'},
                        format='json')
        self.assertEqual(r.status_code, 201)
        change = ExternalChange.objects.get()
        p = {'id': 1, 'client': '103-1', 'hours_per_day': 4, 'parts': [(LINER, 32, 'Colectores')],
             'external': {(LINER, 'Colectores'): [(change.day, change.pk)]}}
        row = due_rows([p], {}, {LINER: (750, 6)}, {}, TODAY)[0]
        self.assertEqual((row['last_change'], row['status']), (date(2026, 10, 1), 'ok'))
        self.assertEqual([(e['kind'], e['external']) for e in row['events'] if e['date'] == date(2026, 10, 1)],
                         [('external', change.pk)])
        self.assertEqual(client.delete(f'/api/servicios/externos/{change.pk}/').status_code, 204)

    def test_a_shared_service_quote_counts_as_invoiced_once_every_part_has_a_later_invoice(self):
        from catalog.models import QuoteRequest
        from .models import Parlor, ServiceQuote
        from .services import invoiced_quotes
        parlor = Parlor.objects.create(client_code='103-1', stalls=8)
        req = QuoteRequest.objects.create(name='Cliente', phone='3312345678', status='APPROVED', from_staff=True)
        ServiceQuote.objects.create(parlor=parlor, request=req, places=[['A', 'G'], ['B', 'G']])
        later = date(2099, 1, 1)
        row = lambda code, d, inv: {'parlor': parlor.pk, 'code': code, 'group': 'G',  # noqa: E731
                                    'events': [{'date': d, 'invoice': inv}]}
        self.assertEqual(invoiced_quotes([row('A', later, 1), row('B', later, None)]), [])  # B changed by someone else
        self.assertEqual(invoiced_quotes([row('A', later, 1), row('B', date(2020, 1, 1), 2)]), [])  # B's is older
        self.assertEqual(invoiced_quotes([row('A', later, 1), row('B', later, 2)]), [req.pk])

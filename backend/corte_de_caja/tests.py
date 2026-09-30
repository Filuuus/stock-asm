"""Tests for the Corte de Caja and Discrepancias logic. SimpleTestCase only:
these functions take plain data, and a test that touched a database would
make Django try to create a test database on the ERP server."""

from datetime import date, datetime
from decimal import Decimal

from django.test import SimpleTestCase

from .date_differences import (
    STATUS_COMERCIAL_ONLY,
    STATUS_CONTABILIDAD_ONLY,
    STATUS_DIFFERENT_AMOUNT,
    STATUS_DIFFERENT_DAY,
    STATUS_DIFFERENT_MONTH,
    STATUS_SAME_DAY,
    STATUS_WRONG_FOLIO,
    _folios_look_alike,
    _match_wrong_folios,
    pair_payments,
)
from .services import PAYMENT_METHOD_TRANSFERENCIA, _payments_without_poliza, _resolve_ledger_events


def item(day, amount):
    return {'date': day, 'amount': Decimal(str(amount))}


def statuses(ledger, comercial):
    return sorted(status for _, _, status in pair_payments(ledger, comercial))


class PairPaymentsTests(SimpleTestCase):
    def test_date_statuses(self):
        cases = [
            (date(2026, 5, 30), date(2026, 5, 30), STATUS_SAME_DAY),
            (date(2026, 5, 28), date(2026, 5, 30), STATUS_DIFFERENT_DAY),
            (date(2026, 6, 1), date(2026, 5, 30), STATUS_DIFFERENT_MONTH),
        ]
        for ledger_day, comercial_day, status in cases:
            with self.subTest(status=status):
                self.assertEqual(statuses([item(ledger_day, 100)], [item(comercial_day, 100)]), [status])

    def test_same_amount_pairs_with_the_nearest_date(self):
        far, near = item(date(2026, 1, 5), 100), item(date(2026, 2, 5), 100)
        matches = pair_payments([far, near], [item(date(2026, 2, 4), 100)])
        paired = [m for m in matches if m[0] and m[1]]
        self.assertEqual(len(paired), 1)
        self.assertIs(paired[0][0][0], near)
        self.assertEqual(statuses([item(date(2026, 1, 5), 100)], []), [STATUS_CONTABILIDAD_ONLY])

    def test_one_payment_split_in_pieces_on_one_side(self):
        # A 4286: one Comercial payment, two polizas of 2,623.04 and 29.87.
        day = date(2026, 3, 2)
        matches = pair_payments([item(day, '2623.04'), item(day, '29.87')], [item(day, '2652.91')])
        self.assertEqual([(len(l), len(c), s) for l, c, s in matches], [(2, 1, STATUS_SAME_DAY)])

    def test_slightly_different_amount_is_one_payment(self):
        # B 19236: $1,753 in Comercial, $1,756 in the poliza, same day.
        day = date(2026, 5, 8)
        self.assertEqual(statuses([item(day, 1756)], [item(day, 1753)]), [STATUS_DIFFERENT_AMOUNT])

    def test_very_different_amounts_stay_one_sided(self):
        # F 20933: 2,753 poliza vs 1,000 payment two days apart.
        self.assertEqual(
            statuses([item(date(2026, 9, 19), 2753)], [item(date(2026, 9, 21), 1000)]),
            [STATUS_COMERCIAL_ONLY, STATUS_CONTABILIDAD_ONLY],
        )

    def test_duplicated_poliza_is_left_on_its_own(self):
        # B 20016: two identical 35,060 polizas, one Comercial payment.
        day = date(2026, 9, 22)
        self.assertEqual(
            statuses([item(day, 35060), item(day, 35060)], [item(day, 35060)]),
            [STATUS_SAME_DAY, STATUS_CONTABILIDAD_ONLY],
        )


class WrongFolioTests(SimpleTestCase):
    def test_folios_that_look_alike(self):
        for a, b in [(20377, 20317), (17263, 17264), (18442, 18842), (12345, 12435)]:
            with self.subTest(a=a, b=b):
                self.assertTrue(_folios_look_alike(a, b))
        for a, b in [(20377, 20377), (20377, 2037), (20377, 20455), (12345, 13254)]:
            with self.subTest(a=a, b=b):
                self.assertFalse(_folios_look_alike(a, b))

    @staticmethod
    def pair(invoice_id, status, day, amount):
        side = [item(day, amount)]
        return {'invoice_id': invoice_id, 'status': status, 'cited_invoice_id': None,
                'ledger': side if status == STATUS_CONTABILIDAD_ONLY else [],
                'comercial': side if status == STATUS_COMERCIAL_ONLY else []}

    def test_payment_and_poliza_on_look_alike_folios_are_joined(self):
        # Ingresos 264 cites F 20317; Comercial applied the payment to F 20377.
        facturas = {1: {'CFOLIO': 20377.0}, 2: {'CFOLIO': 20317.0}}
        pairs = _match_wrong_folios([
            self.pair(2, STATUS_CONTABILIDAD_ONLY, date(2026, 5, 27), 2070),
            self.pair(1, STATUS_COMERCIAL_ONLY, date(2026, 5, 28), 2070),
        ], facturas)
        self.assertEqual(len(pairs), 1)
        self.assertEqual((pairs[0]['invoice_id'], pairs[0]['status'], pairs[0]['cited_invoice_id']),
                         (1, STATUS_WRONG_FOLIO, 2))
        self.assertTrue(pairs[0]['ledger'] and pairs[0]['comercial'])

    def test_every_payment_is_checked_when_earlier_rows_are_joined(self):
        facturas = {1: {'CFOLIO': 20377.0}, 2: {'CFOLIO': 20317.0}, 3: {'CFOLIO': 18442.0}, 4: {'CFOLIO': 18842.0}}
        pairs = _match_wrong_folios([
            self.pair(2, STATUS_CONTABILIDAD_ONLY, date(2026, 5, 27), 2070),
            self.pair(1, STATUS_COMERCIAL_ONLY, date(2026, 5, 28), 2070),
            self.pair(3, STATUS_COMERCIAL_ONLY, date(2026, 7, 9), 380),
            self.pair(4, STATUS_CONTABILIDAD_ONLY, date(2026, 7, 9), 380),
        ], facturas)
        self.assertEqual([(p['invoice_id'], p['status']) for p in pairs],
                         [(1, STATUS_WRONG_FOLIO), (3, STATUS_WRONG_FOLIO)])

    def test_not_joined_when_amount_date_or_folio_differ(self):
        facturas = {1: {'CFOLIO': 20377.0}, 2: {'CFOLIO': 20317.0}, 3: {'CFOLIO': 19000.0}}
        payment = (1, STATUS_COMERCIAL_ONLY, date(2026, 5, 28), 2070)
        for poliza in [(2, date(2026, 5, 27), 2075), (2, date(2026, 6, 10), 2070), (3, date(2026, 5, 27), 2070)]:
            with self.subTest(poliza=poliza):
                pairs = _match_wrong_folios(
                    [self.pair(*payment), self.pair(poliza[0], STATUS_CONTABILIDAD_ONLY, *poliza[1:])], facturas,
                )
                self.assertEqual(len(pairs), 2)


def factura(invoice_id, folio, total):
    return {'CIDDOCUMENTO': invoice_id, 'CFOLIO': float(folio), 'CTOTAL': total, 'CPENDIENTE': 0,
            'CRAZONSOCIAL': 'RANCHO EL NOGAL SA', 'CIDCONCEPTODOCUMENTO': 1, 'CFECHA': datetime(2026, 1, 1)}


def line(poliza, referencia, day, amount, abono=True, cuenta=50):
    """(IdPoliza, Referencia, Fecha, Concepto, Importe, TipoMovto, IdCuenta)"""
    return (poliza, referencia, datetime(day.year, day.month, day.day), 'RANCHO EL NOGAL SA', amount, abono, cuenta)


class LedgerEventsTests(SimpleTestCase):
    facturas = [factura(1, 100, 1000)]
    banks = {900: ('100102001', 'BBVA BANCOMER 0161')}
    lines = [
        line(10, 'F-100', date(2026, 1, 10), 400),
        line(10, '', date(2026, 1, 10), 400, abono=False, cuenta=900),  # the bank debit
        line(11, 'F-100', date(2026, 2, 10), 600),
        line(12, 'F-100', date(2026, 3, 1), 0.02),  # rounding leftover, not a collection
    ]

    def events(self, date_from, date_to):
        return _resolve_ledger_events(self.facturas, self.lines, {1: 'F'}, self.banks, date_from, date_to)

    def test_partial_payment_is_an_abono_with_its_bank(self):
        events, covered = self.events(date(2026, 1, 1), date(2026, 1, 31))
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual((event['event_date'], event['amount'], event['abono']), (date(2026, 1, 10), Decimal('400'), True))
        self.assertEqual((event['suggested_method'], event['bank']), (PAYMENT_METHOD_TRANSFERENCIA, 'BBVA BANCOMER 0161'))
        self.assertEqual(covered, {1})

    def test_payment_that_completes_the_invoice_is_not_an_abono(self):
        events, _ = self.events(date(2026, 2, 1), date(2026, 2, 28))
        self.assertEqual([(e['amount'], e['abono'], e['bank']) for e in events], [(Decimal('600'), False, None)])

    def test_cents_are_not_events_and_the_invoice_stays_covered(self):
        # A day with no real event must not look like "the ledger doesn't
        # cover this invoice".
        events, covered = self.events(date(2026, 3, 1), date(2026, 3, 31))
        self.assertEqual(events, [])
        self.assertEqual(covered, {1})


class PaymentsWithoutPolizaTests(SimpleTestCase):
    facturas = [factura(1, 4479, 2840), factura(2, 20734, 3826), factura(3, 100, 500)]
    period = (date(2026, 8, 1), date(2026, 8, 31))

    @staticmethod
    def application(invoice_id, day, amount, serie='BBV', folio=19686.0):
        """(invoice, payment, payment date, applied date, amount, serie, folio)"""
        when = datetime(day.year, day.month, day.day)
        return (invoice_id, 77, when, when, amount, serie, folio)

    def test_each_row_is_the_amount_applied_to_that_invoice(self):
        # BBV 19686: one $6,666 payment applied to two re-issued invoices.
        rows = _payments_without_poliza(
            self.facturas,
            [self.application(1, date(2026, 8, 6), 2840.0), self.application(2, date(2026, 8, 6), 3826.0)],
            set(), *self.period,
        )
        self.assertEqual([(r['invoice_id'], r['amount'], r['pago']) for r in rows],
                         [(1, Decimal('2840'), 'BBV 19686'), (2, Decimal('3826'), 'BBV 19686')])

    def test_what_is_left_out(self):
        cases = {
            'invoice the ledger already covers': (self.application(3, date(2026, 8, 6), 500.0), {3}),
            'payment outside the period': (self.application(3, date(2026, 9, 1), 500.0), set()),
            'cents': (self.application(3, date(2026, 8, 6), 0.5), set()),
            'invoice that is not a candidate': (self.application(99, date(2026, 8, 6), 500.0), set()),
        }
        for name, (application, covered) in cases.items():
            with self.subTest(name):
                self.assertEqual(_payments_without_poliza(self.facturas, [application], covered, *self.period), [])

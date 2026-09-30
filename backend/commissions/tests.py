"""Tests for the commission and ledger logic. SimpleTestCase only: these
functions take plain data, and a test that touched a database would make
Django try to create a test database on the ERP server."""

from datetime import date, datetime
from decimal import Decimal

from django.test import SimpleTestCase

from .models import CommissionCategoryRate
from .services import (
    BIONAT_SUPPLIER_NAME,
    NORTHWEST_RUBBER_SUPPLIER_NAME,
    _classify_line,
    _effective_rate,
    _extract_folio_tokens,
    _paid_dates_from_ledger,
    _rate_code_for,
    attribute_ledger_payments,
)

SERIES = {1: 'F', 2: 'B'}


def factura(invoice_id, folio, total, client='RANCHO EL NOGAL SA', concepto=1, pendiente=0, fecha=date(2026, 1, 1)):
    return {
        'CIDDOCUMENTO': invoice_id, 'CFOLIO': float(folio), 'CTOTAL': total, 'CPENDIENTE': pendiente,
        'CRAZONSOCIAL': client, 'CIDCONCEPTODOCUMENTO': concepto,
        'CFECHA': datetime(fecha.year, fecha.month, fecha.day),
    }


def line(poliza, referencia, day, amount, concepto='RANCHO EL NOGAL SA', abono=True, cuenta=50):
    """(IdPoliza, Referencia, Fecha, Concepto, Importe, TipoMovto, IdCuenta)"""
    return (poliza, referencia, datetime(day.year, day.month, day.day), concepto, amount, abono, cuenta)


def amounts(accepted, invoice_id):
    return {day: sum(a for _, a in entries) for day, entries in accepted.get(invoice_id, {}).items()}


class AttributeLedgerPaymentsTests(SimpleTestCase):
    def test_both_reference_forms_and_series(self):
        # The ledger writes "{serie}-{folio}" or "{serie} {folio}", any case.
        facturas = [factura(1, 100, 500), factura(2, 19778, 800, concepto=2)]
        lines = [line(10, 'F-100', date(2026, 1, 5), 500), line(11, 'b 19778', date(2026, 1, 6), 800)]
        accepted = attribute_ledger_payments(facturas, lines, SERIES)
        self.assertEqual(amounts(accepted, 1), {date(2026, 1, 5): 500})
        self.assertEqual(amounts(accepted, 2), {date(2026, 1, 6): 800})

    def test_lines_are_netted_by_movement_type(self):
        lines = [
            line(10, 'F-100', date(2026, 1, 5), 600000),
            line(10, 'F-100', date(2026, 1, 5), 100000, abono=False),
        ]
        accepted = attribute_ledger_payments([factura(1, 100, 5300000)], lines, SERIES)
        self.assertEqual(amounts(accepted, 1), {date(2026, 1, 5): 500000})

    def test_unique_folio_does_not_need_the_client_name(self):
        # F 20933: the ledger spelled the client differently and a 9,000
        # payment was dropped.
        lines = [line(10, 'F-20933', date(2026, 8, 6), 9000, concepto='OTRO NOMBRE')]
        accepted = attribute_ledger_payments([factura(1, 20933, 29182)], lines, SERIES)
        self.assertEqual(amounts(accepted, 1), {date(2026, 8, 6): 9000})

    def test_shared_folio_goes_to_the_client_the_ledger_names(self):
        facturas = [factura(1, 100, 500, client='ALFA SA'), factura(2, 100, 500, client='BETA SA')]
        lines = [line(10, 'F-100', date(2026, 1, 5), 500, concepto='PAGO BETA SA')]
        accepted = attribute_ledger_payments(facturas, lines, SERIES)
        self.assertNotIn(1, accepted)
        self.assertEqual(amounts(accepted, 2), {date(2026, 1, 5): 500})

    def test_duplicated_poliza_counts_once(self):
        # B 20016: two identical 35,060 polizas for one payment.
        lines = [line(167, 'F-100', date(2026, 9, 22), 35060), line(170, 'F-100', date(2026, 9, 22), 35060)]
        accepted = attribute_ledger_payments([factura(1, 100, 35060)], lines, SERIES)
        self.assertEqual(amounts(accepted, 1), {date(2026, 9, 22): 35060})

    def test_lone_overpayment_is_kept(self):
        # 1,830 received on a 1,744.01 invoice is real cash.
        lines = [line(10, 'F-100', date(2026, 1, 5), 1830)]
        accepted = attribute_ledger_payments([factura(1, 100, 1744.01)], lines, SERIES)
        self.assertEqual(amounts(accepted, 1), {date(2026, 1, 5): 1830})

    def test_payment_citing_the_wrong_invoice_moves_to_the_one_it_fits(self):
        # 33,194 cited against a 10,290 invoice; the paid one was the
        # neighbouring folio of the same client.
        facturas = [factura(1, 200, 10290), factura(2, 201, 33194)]
        lines = [line(4, 'F-200', date(2026, 2, 1), 10290), line(5, 'F-200', date(2026, 2, 3), 33194)]
        accepted = attribute_ledger_payments(facturas, lines, SERIES)
        self.assertEqual(amounts(accepted, 1), {date(2026, 2, 1): 10290})
        self.assertEqual(amounts(accepted, 2), {date(2026, 2, 3): 33194})

    def test_misfit_without_a_clear_home_stays_where_the_ledger_cites_it(self):
        # Two invoices it could belong to: ambiguous, so it isn't moved.
        facturas = [factura(1, 200, 10290), factura(2, 201, 33194), factura(3, 202, 33194)]
        lines = [line(4, 'F-200', date(2026, 2, 1), 10290), line(5, 'F-200', date(2026, 2, 3), 33194)]
        accepted = attribute_ledger_payments(facturas, lines, SERIES)
        self.assertEqual(amounts(accepted, 1), {date(2026, 2, 1): 10290, date(2026, 2, 3): 33194})
        self.assertNotIn(2, accepted)
        self.assertNotIn(3, accepted)


class PaidDatesTests(SimpleTestCase):
    accepted = {1: {date(2026, 1, 30): [(10, 500.0)], date(2026, 2, 27): [(11, 500.0)]}}

    def test_paid_on_the_installment_that_completes_the_total(self):
        paid = _paid_dates_from_ledger([factura(1, 100, 1000)], self.accepted)
        self.assertEqual(paid[1].date(), date(2026, 2, 27))

    def test_never_reaching_the_total_stays_unresolved(self):
        # The $5.3M invoice whose installments only add up to ~$2.8M.
        self.assertEqual(_paid_dates_from_ledger([factura(1, 100, 5000)], self.accepted), {})

    def test_partly_credit_noted_invoice_is_paid_once_the_cash_part_is_covered(self):
        paid = _paid_dates_from_ledger([factura(1, 100, 1000)], self.accepted, cash_due={1: 500})
        self.assertEqual(paid[1].date(), date(2026, 1, 30))


class RateTests(SimpleTestCase):
    rate = CommissionCategoryRate(code='R', base_rate=Decimal('0.06'), decay_rate_per_week=Decimal('0.005'))

    def test_decay_is_a_weekly_step_starting_on_the_first_late_day(self):
        expected = {-3: '0.06', 0: '0.06', 1: '0.055', 7: '0.055', 8: '0.05', 84: '0', 200: '0'}
        for days_late, rate in expected.items():
            with self.subTest(days_late=days_late):
                self.assertEqual(_effective_rate(self.rate, days_late), Decimal(rate))

    def test_late_penalty_is_taken_once_when_late(self):
        # GEA parts: 6% on time; late, 4% the first week and then the weekly decay.
        parts = CommissionCategoryRate(code='R', base_rate=Decimal('0.06'), decay_rate_per_week=Decimal('0.005'),
                                       late_penalty=Decimal('0.015'))
        expected = {-15: '0.06', 0: '0.06', 1: '0.04', 7: '0.04', 8: '0.035', 19: '0.03', 56: '0.005', 63: '0', 98: '0'}
        for days_late, rate in expected.items():
            with self.subTest(days_late=days_late):
                self.assertEqual(_effective_rate(parts, days_late), Decimal(rate))

    def test_missing_rate_row_pays_nothing(self):
        self.assertEqual(_effective_rate(None, 0), Decimal('0'))

    def test_categories(self):
        brands = {1: BIONAT_SUPPLIER_NAME, 2: NORTHWEST_RUBBER_SUPPLIER_NAME, 3: 'DETERGENTES SURGE', 4: 'GEA'}

        def producto(codigo='7021-1', brand=4, line2=None, tipo=1, nombre='PEZONERA'):
            return {'CCODIGOPRODUCTO': codigo, 'CIDVALORCLASIFICACION1': brand, 'CIDVALORCLASIFICACION2': line2,
                    'CTIPOPRODUCTO': tipo, 'CNOMBREPRODUCTO': nombre}

        cases = [
            (producto(codigo='ZERO-1', brand=1), 'ZERO'),
            (producto(brand=1, tipo=3), 'B'),
            (producto(tipo=3), 'S'),
            (producto(brand=2), 'R_NW'),
            (producto(codigo='4999-1115-0001'), 'R_NW'),
            (producto(line2=3), 'R_CHEM'),
            (producto(nombre='Ventilador 52"'), 'R_FAN'),
            (producto(), 'R'),
        ]
        for prod, category in cases:
            with self.subTest(category=category, codigo=prod['CCODIGOPRODUCTO']):
                self.assertEqual(_classify_line(prod, brands, {'ZERO-1'}), category)

    def test_rate_codes(self):
        self.assertIsNone(_rate_code_for('ZERO', 'ZONA1'))
        self.assertEqual(_rate_code_for('S', 'ZONA2'), 'S_SALESPERSON')
        self.assertEqual(_rate_code_for('S', 'SERVICIOS'), 'S_SERVICIOS')
        self.assertEqual(_rate_code_for('R_NW', 'OFICINA'), 'R_NW')


class FolioTokenTests(SimpleTestCase):
    def test_folios_in_a_reference_text(self):
        self.assertEqual(_extract_folio_tokens('F 20933 y 20934'), {'20933', '20934'})
        self.assertEqual(_extract_folio_tokens('12'), set())

    def test_range_shorthand(self):
        # "4395-96" means folios 4395 and 4396.
        self.assertEqual(_extract_folio_tokens('4395-96'), {'4395', '4396'})
        self.assertEqual(_extract_folio_tokens('20933-20934'), {'20933', '20934'})

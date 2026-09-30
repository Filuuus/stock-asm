"""Tests for the invoice dialog rules. SimpleTestCase only: these functions
take plain data, and a test that touched a database would make Django try to
create a test database on the ERP server."""

from datetime import date

from django.test import SimpleTestCase

from corte_de_caja.date_differences import _folios_look_alike

from .services import _look_alike_folios, not_counted_reason


class PolizaCountingTests(SimpleTestCase):
    invoice_date = date(2026, 5, 1)

    def reason(self, is_payment=True, poliza_date=date(2026, 5, 10), shared=False, names_client=False):
        return not_counted_reason(is_payment, poliza_date, self.invoice_date, shared, names_client)

    def test_a_collection_poliza_counts(self):
        self.assertEqual(self.reason(), '')
        # A payment dated before its invoice (an advance) still counts.
        self.assertEqual(self.reason(poliza_date=date(2026, 4, 20)), '')

    def test_what_does_not_count(self):
        self.assertIn('No es una póliza de cobro', self.reason(is_payment=False))
        # F 19417 is cited by 2017 polizas: an older invoice with the same number.
        self.assertIn('más de un año antes', self.reason(poliza_date=date(2017, 3, 1)))
        self.assertIn('misma serie y folio', self.reason(shared=True))
        self.assertEqual(self.reason(shared=True, names_client=True), '')


class LookAlikeFolioTests(SimpleTestCase):
    def test_generated_folios_match_the_tab_rule(self):
        folios = _look_alike_folios(20377)
        self.assertIn(20317, folios)
        self.assertIn(23077, folios)  # two neighbouring digits swapped
        self.assertNotIn(20377, folios)
        self.assertTrue(all(_folios_look_alike(20377, f) for f in folios))

from django.test import SimpleTestCase

from .services import summarize


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

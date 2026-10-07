"""Tests for the fleet GPS log's pure functions, on made-up Zeek/Notion data."""

from datetime import datetime

from django.test import SimpleTestCase

from .services import LOCAL_TZ, parse_zeek_trips, summarize_day, summarize_month, zeek_coord, zeek_time


def point(odo, fecha='/Date(1759363200000)/', lat=2053123, lon=-10275000, ng=None):
    return {'odo': str(odo), 'Fecha': fecha, 'Latitud': lat, 'Longitud': lon, 'ng': ng}


def log_page(name, day, km, odometer, route=None):
    return {'properties': {
        'Vehículo': {'type': 'title', 'title': [{'plain_text': name}]},
        'Fecha': {'type': 'date', 'date': {'start': day}},
        'Recorrido Diario': {'type': 'number', 'number': km},
        'Odómetro Total': {'type': 'number', 'number': odometer},
        'Ruta': {'type': 'url', 'url': route},
    }}


class ZeekParsingTests(SimpleTestCase):
    def test_coord_is_degrees_and_decimal_minutes(self):
        self.assertAlmostEqual(zeek_coord(2053123), 20 + 53.123 / 60)
        self.assertAlmostEqual(zeek_coord(-10230000), -(102 + 30 / 60))

    def test_time_ignores_offset_suffix(self):
        expected = datetime(2025, 10, 1, 18, 0, tzinfo=LOCAL_TZ)
        self.assertEqual(zeek_time('/Date(1759363200000)/'), expected)
        self.assertEqual(zeek_time('/Date(1759363200000-0600)/'), expected)

    def test_parse_unwraps_xml_reverses_and_drops_empty_trips(self):
        text = '<string>[{"id": 2, "listaUbicaciones": [1]}, {"id": 1, "listaUbicaciones": [1]}, ' \
               '{"id": 0, "listaUbicaciones": []}]</string>'
        self.assertEqual([t['id'] for t in parse_zeek_trips(text)], [1, 2])

    def test_parse_rejects_response_without_json(self):
        with self.assertRaises(ValueError):
            parse_zeek_trips('<error>licencia inválida</error>')


class SummaryTests(SimpleTestCase):
    def test_day_km_spans_first_to_last_point(self):
        trips = [
            {'listaUbicaciones': [point(100000), point(112500, ng='Bodega')]},
            {'listaUbicaciones': [point(112500), point(130250)]},
        ]
        km, route, blocks = summarize_day(trips)
        self.assertEqual(km, 30.25)
        self.assertEqual(route.count('/') - 'https://www.google.com/maps/dir/'.count('/'), 2)  # start + 2 stops
        self.assertEqual(len(blocks), 2)

    def test_month_sums_km_keeps_highest_odometer_and_sorts_days(self):
        summary = summarize_month([
            log_page('Hilux', '2026-09-02', 10.1, 1010.1, 'https://maps/b'),
            log_page('Hilux', '2026-09-01', 5.05, 1000.0, 'https://maps/a'),
            log_page('Fiat', '2026-09-01', None, 0),
        ])
        self.assertEqual(summary['Hilux']['km'], 15.15)
        self.assertEqual(summary['Hilux']['odometer'], 1010.1)
        self.assertEqual([d for d, _, _ in summary['Hilux']['days']], ['2026-09-01', '2026-09-02'])
        self.assertEqual(summary['Fiat']['km'], 0)

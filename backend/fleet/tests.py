"""Tests for the fleet GPS log's pure functions, on made-up Zeek/Notion data."""

from datetime import date, datetime
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from .models import VehicleDayKm, VehicleStop
from .services import LOCAL_TZ, close_month, notion_stops, store_km, parse_zeek_trips, summarize_day, summarize_month, zeek_coord, zeek_time


def point(odo, fecha='/Date(1759363200000)/', lat=2053123, lon=-10275000, ng=None):
    return {'odo': str(odo), 'Fecha': fecha, 'Latitud': lat, 'Longitud': lon, 'ng': ng}


def log_page(name, day, km, odometer, route=None, page_id=None):
    return {'id': page_id or f'{name}-{day}', 'properties': {
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
        self.assertEqual(summary['Hilux']['page_ids'], ['Hilux-2026-09-02', 'Hilux-2026-09-01'])


class CloseMonthTests(SimpleTestCase):
    @patch('fleet.services.notion')
    @patch('fleet.services.notion_query')
    def test_archives_daily_entries_and_skips_vehicles_already_closed(self, query, notion):
        query.side_effect = [
            [log_page('Reporte Mensual - Fiat', '2026-09-01', 7, 500)],
            [log_page('Hilux', '2026-09-01', 5, 1000), log_page('Fiat', '2026-09-03', 7, 500)],
        ]
        close_month(date(2026, 9, 1), date(2026, 9, 30), lambda msg: None)
        calls = [(c.args[0], c.args[1]) for c in notion.call_args_list]
        # Only Hilux gets a monthly entry, created before its daily entry is archived; Fiat's
        # leftover daily entry is archived too.
        self.assertEqual(calls, [
            ('POST', 'pages'),
            ('PATCH', 'pages/Hilux-2026-09-01'),
            ('PATCH', 'pages/Fiat-2026-09-03'),
        ])
        self.assertEqual(notion.call_args_list[1].args[2], {'archived': True})


@override_settings(ZEEK_FLEET={'111': 'card-a', '222': 'card-b', '333': 'card-c'})
class StoreKmTests(TestCase):
    @patch('fleet.services.fetch_zeek_trips')
    def test_stores_km_and_zero_and_skips_units_zeek_failed_on(self, fetch):
        trips = [{'listaUbicaciones': [point(100000), point(130250)]}]

        def fake_fetch(imei, start, end):
            if imei == '333':
                raise OSError('down')
            return trips if imei == '111' else []
        fetch.side_effect = fake_fetch
        store_km(date(2026, 10, 2), date(2026, 10, 3), lambda msg: None)
        store_km(date(2026, 10, 3), date(2026, 10, 3), lambda msg: None)  # re-run overwrites, no duplicates
        rows = {(r.imei, r.day.isoformat()): float(r.km) for r in VehicleDayKm.objects.all()}
        self.assertEqual(rows, {
            ('111', '2026-10-02'): 30.25, ('222', '2026-10-02'): 0,
            ('111', '2026-10-03'): 30.25, ('222', '2026-10-03'): 0,
        })
        self.assertEqual(VehicleStop.objects.filter(imei='111').count(), 2)  # one per day, re-run replaced


class NotionStopsTests(SimpleTestCase):
    def test_reads_trip_ends_as_stops_until_the_next_trip(self):
        def callout(start, end, lat, lng):
            return {'callout': {'rich_text': [
                {'text': {'content': f'🟢 {start}  ➔  🔴 {end}\nDestino: '}},
                {'text': {'content': 'Ver ubicación', 'link': {'url': f'https://www.google.com/maps?q={lat}%2C{lng}'}}},
                {'text': {'content': '\n⏱️ 3 km recorridos en 8 min'}}]}}
        stops = notion_stops(date(2026, 10, 2), [callout('08:52 AM', '09:10 AM', 20.5, -102.7),
                                                   callout('01:05 PM', '01:30 PM', 20.6, -102.8), {'divider': {}}])
        self.assertEqual([(s['arrive'].hour, s['arrive'].minute) for s in stops], [(9, 10), (13, 30)])
        self.assertEqual(stops[0]['leave'], datetime(2026, 10, 2, 13, 5, tzinfo=LOCAL_TZ))
        self.assertIsNone(stops[1]['leave'])
        self.assertEqual((stops[1]['lat'], stops[1]['lng']), (20.6, -102.8))

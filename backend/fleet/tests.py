"""Tests for the fleet GPS log's pure functions, on made-up Zeek/Notion data."""

from datetime import date, datetime, timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from .models import VehicleDayKm, VehicleStop
from profitability.models import SavedPlace

from .matching import StopMatcher
from .notion import day_blocks, notion_stops, renamed, stop_name
from .route_sheets import Month, build_workbook, calendar_guesses, service_invoices, town
from .services import close_month, store_km, summarize_month
from .timeline import legs, stops
from .zeek import LOCAL_TZ, parse_zeek_trips, zeek_coord, zeek_time


def point(odo, fecha='/Date(1759363200000)/', lat=2053123, lon=-10275000, ng=None):
    return {'odo': str(odo), 'Fecha': fecha, 'Latitud': lat, 'Longitud': lon, 'ng': ng}


def log_page(name, day, km, odometer, route=None, page_id=None):
    return {'id': page_id or f'{name}-{day}', 'properties': {
        'Vehículo': {'type': 'title', 'title': [{'plain_text': name}]},
        'Fecha': {'type': 'date', 'date': {'start': day}},
        'Recorrido Diario': {'type': 'number', 'number': km},
        'Kilometraje Total': {'type': 'number', 'number': odometer},
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
    def test_day_blocks_one_callout_per_leg_and_route_through_parked_stops(self):
        trips = [
            {'listaUbicaciones': [point(100000), point(112500, ng='Bodega')]},
            {'listaUbicaciones': [point(112500), point(130250)]},
        ]
        blocks, route = day_blocks(legs(trips), StopMatcher([]), {})
        self.assertEqual(route.count('/') - 'https://www.google.com/maps/dir/'.count('/'), 2)  # start + 2 stops
        self.assertEqual(len(blocks), 2)
        text = ''.join(t['text']['content'] for t in blocks[0]['callout']['rich_text'])
        self.assertIn('🟢', text)
        self.assertIn('🔴', text)
        self.assertIn('Bodega', text)
        self.assertIn('12.5 km', text)

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
        self.assertEqual(summary['Hilux']['pages'], [('Hilux-2026-09-02', '2026-09-02'), ('Hilux-2026-09-01', '2026-09-01')])


@patch('fleet.services.vehicle_imeis', lambda: {'hilux': '111', 'fiat': '222', 'isuzu': '333'})
@patch('fleet.services.rescue_notion_stops')
@patch('fleet.services.notion')
@patch('fleet.services.notion_query')
class CloseMonthTests(TestCase):
    def test_archives_daily_entries_and_skips_vehicles_already_closed(self, query, notion, rescue):
        VehicleDayKm.objects.create(imei='111', day=date(2026, 9, 1), km=5)
        VehicleDayKm.objects.create(imei='222', day=date(2026, 9, 3), km=7)
        query.side_effect = [
            [log_page('Reporte Mensual - Fiat', '2026-09-01', 7, 500)],
            [log_page('Hilux', '2026-09-01', 5, 1000), log_page('Fiat', '2026-09-03', 7, 500)],
        ]
        close_month(date(2026, 9, 1), date(2026, 9, 30), lambda msg: None)
        rescue.assert_called_once()
        calls = [(c.args[0], c.args[1]) for c in notion.call_args_list]
        # Only Hilux gets a monthly entry, created before its daily entry is archived; Fiat's
        # leftover daily entry is archived too.
        self.assertEqual(calls, [
            ('POST', 'pages'),
            ('PATCH', 'pages/Hilux-2026-09-01'),
            ('PATCH', 'pages/Fiat-2026-09-03'),
        ])
        self.assertEqual(notion.call_args_list[1].args[2], {'archived': True})

    def test_keeps_daily_entries_whose_day_is_not_stored_locally(self, query, notion, rescue):
        VehicleDayKm.objects.create(imei='111', day=date(2026, 9, 1), km=5)
        query.side_effect = [[], [
            log_page('Hilux', '2026-09-01', 5, 1000), log_page('Hilux', '2026-09-02', 8, 1008),
            log_page('Camión nuevo', '2026-09-02', 3, 300),  # no card matches this name
        ]]
        close_month(date(2026, 9, 1), date(2026, 9, 30), lambda msg: None)
        archived = [c.args[1] for c in notion.call_args_list if c.args[0] == 'PATCH']
        self.assertEqual(archived, ['pages/Hilux-2026-09-01'])


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

    @patch('fleet.services.fetch_zeek_trips')
    def test_never_replaces_a_stored_day_with_fewer_km(self, fetch):
        # 209.88 km: not exact in binary, so an equal re-read must still count as equal
        full = [{'listaUbicaciones': [point(100000), point(112500)]}, {'listaUbicaciones': [point(112500), point(309880)]}]
        fetch.return_value = full
        store_km(date(2026, 10, 2), date(2026, 10, 2), lambda msg: None)
        for later in ([], full[:1]):  # Zeek answers empty, then with only part of the day
            fetch.return_value = later
            store_km(date(2026, 10, 2), date(2026, 10, 2), lambda msg: None)
        self.assertEqual(float(VehicleDayKm.objects.get(imei='111', day=date(2026, 10, 2)).km), 209.88)
        self.assertEqual(VehicleStop.objects.filter(imei='111', day=date(2026, 10, 2)).count(), 2)

        fetch.return_value = full
        logs = []
        store_km(date(2026, 10, 2), date(2026, 10, 2), logs.append)
        self.assertFalse([m for m in logs if 'conservan' in m], logs)


def moving(minute, speed, lat=2048000, odo=0):
    return {**point(odo, fecha=f'/Date({1759363200000 + minute * 60000})/', lat=lat), 'Velocidad': speed}


# One trip: warms up, drives, idles 4 min at a client, a 1-min red light, then idles 2 min before turning off.
TRIP = [moving(0, 0, odo=1000), moving(1, 0, odo=1000), moving(2, 40, 2049000, 2000),
        moving(5, 0, 2050000, 5000), moving(6, 2, 2050001, 5000), moving(9, 0, 2050000, 5000),
        moving(10, 50, 2051000, 7000), moving(11, 0, 2052000, 8000), moving(12, 0, 2052000, 8000),
        moving(13, 30, 2053000, 9000), moving(14, 0, 2054000, 10000), moving(16, 0, 2054000, 10000)]


class TimelineTests(SimpleTestCase):
    def test_engine_on_stop_splits_the_trip_and_arrival_is_when_it_stopped_moving(self):
        day = legs([{'listaUbicaciones': TRIP}, {'listaUbicaciones': [moving(30, 0), moving(31, 20)]}])
        self.assertEqual([(l['start'].minute, l['end'].minute, l['start_kind'], l['end_kind']) for l in day[:2]],
                         [(0, 5, 'parked', 'idle'), (9, 14, 'idle', 'parked')])  # departure stays at ignition on
        self.assertEqual([l['km'] for l in day[:2]], [4.0, 5.0])
        self.assertEqual(day[0]['leave'].minute, 9)
        self.assertEqual(day[1]['leave'].minute, 30)  # parked until the next trip starts
        self.assertIsNone(day[-1]['leave'])
        rows = stops(day)
        self.assertEqual([(s['arrive'].minute, s['engine_on']) for s in rows[:2]], [(5, True), (14, False)])
        self.assertAlmostEqual(rows[0]['lat'], zeek_coord(2050000))

    def test_points_without_speed_count_as_moving(self):
        day = legs([{'listaUbicaciones': [point(0), point(500), point(900)]}])
        self.assertEqual(len(day), 1)
        self.assertEqual(day[0]['km'], 0.9)


def place(name, lat, lng, client_ids=(), kind='', personal=False, approximate=False):
    return SavedPlace(name=name, lat=lat, lng=lng, client_ids=list(client_ids), kind=kind, personal=personal,
                      approximate=approximate)


class MatchingTests(SimpleTestCase):
    places = [
        place('Oficina', 20.0, -102.0, kind='base'),
        place('Rancho', 20.1, -102.0, [7, 8]),
        place('Bookmark', 20.1001, -102.0),                     # nearer, but nobody checked it: never names
        place('Pueblo', 20.2, -102.0, [9], approximate=True),   # town-level pins never name a stop
        place('Tacos', 20.3, -102.0, kind='spot'),
        place('Casa', 20.4, -102.0, kind='spot', personal=True),
        place('', 20.5, -102.0, kind='spot'),                    # looked at, left unnamed
    ]

    def test_names_from_bases_clients_and_spots_only(self):
        matcher = StopMatcher(self.places)
        names = {7: 'ANA', 8: 'BETO'}
        line = lambda lat: stop_name(matcher.match(lat, -102.0), names)
        self.assertEqual(line(20.0021), '\n🏢 Oficina')            # ~230 m: still the base (400 m)
        self.assertEqual(line(20.1002), '\n👤 ANA / BETO (~22 m)')  # every client of a shared place
        self.assertEqual(line(20.2), '')
        self.assertEqual(line(20.3010), '\n📌 Tacos')             # ~110 m (spots: 150 m)
        self.assertEqual(line(20.3020), '')                       # ~220 m
        self.assertEqual(line(20.4), '\n📌 Parada personal')
        self.assertEqual(line(20.5), '')

    def test_renamed_replaces_only_the_name_line(self):
        rich = [{'text': {'content': '🟢 08:00 AM  ➔  🔴 09:00 AM\nDestino: '}},
                {'text': {'content': 'Ver mapa', 'link': {'url': 'https://www.google.com/maps?q=20.1,-102.0'}}},
                {'text': {'content': '\n👤 VIEJO (~5 m)'}}, {'text': {'content': '\n⏱️ 3 km en 8 min'}}]
        new = renamed(rich, '\n📌 Tacos')
        self.assertEqual([t['text']['content'] for t in new][2:], ['\n📌 Tacos', '\n⏱️ 3 km en 8 min'])
        self.assertEqual(new[1]['text']['link']['url'], 'https://www.google.com/maps?q=20.1,-102.0')
        self.assertEqual(len(renamed(rich, '')), 3)


class NotionStopsTests(SimpleTestCase):
    def test_reads_old_trip_callouts_as_stops_until_the_next_trip(self):
        def callout(start, end, lat, lng):
            return {'callout': {'rich_text': [
                {'text': {'content': f'🟢 {start}  ➔  🔴 {end}\nDestino: '}},
                {'text': {'content': 'Ver ubicación', 'link': {'url': f'https://www.google.com/maps?q={lat}%2C{lng}'}}},
                {'text': {'content': '\n⏱️ 3 km recorridos en 8 min'}}]}}
        stops_ = notion_stops(date(2026, 10, 2), [callout('08:52 AM', '09:10 AM', 20.5, -102.7),
                                                  callout('01:05 PM', '01:30 PM', 20.6, -102.8), {'divider': {}}])
        self.assertEqual([(s['arrive'].hour, s['arrive'].minute) for s in stops_], [(9, 10), (13, 30)])
        self.assertEqual(stops_[0]['leave'], datetime(2026, 10, 2, 13, 5, tzinfo=LOCAL_TZ))
        self.assertIsNone(stops_[1]['leave'])
        self.assertEqual((stops_[1]['lat'], stops_[1]['lng']), (20.6, -102.8))

    def test_written_callouts_read_back_as_the_same_stops(self):
        day = legs([{'listaUbicaciones': TRIP}])
        blocks, _ = day_blocks(day, StopMatcher([]), {})
        read = notion_stops(date(2025, 10, 1), blocks)
        self.assertEqual([(s['arrive'], s['engine_on']) for s in read], [(s['arrive'], s['engine_on']) for s in stops(day)])
        self.assertEqual(read[0]['leave'], day[0]['leave'])


class FakeErp:
    def __init__(self, invoices=(), zone_of=None):
        self.clients = {7: ('C-7', 'ANA'), 8: ('C-8', 'BETO'), 9: ('C-9', 'CRUZ')}
        self.towns, self.zone_of = {}, zone_of or {7: 1, 8: 1, 9: 1}
        self.invoices, self.service_invoices = list(invoices), []

    def sold(self, cid, day, before=1, after=2):
        return [x for x in self.invoices if x[0] == cid and (day - x[1]).days <= before and (x[1] - day).days <= after]

    def name(self, cid):
        return self.clients[cid][1]


def stop(imei, hour, minute, minutes, lat, lng=-102.0, day=date(2026, 11, 3), engine_on=False):
    arrive = datetime(day.year, day.month, day.day, hour, minute, tzinfo=LOCAL_TZ)
    return VehicleStop(imei=imei, day=day, arrive=arrive, leave=arrive + timedelta(minutes=minutes), lat=lat, lng=lng,
                       engine_on=engine_on, source='zeek')


@override_settings(FLEET_SERVICE_IMEI='crew')
class RouteSheetTests(SimpleTestCase):
    places = [place('Oficina', 20.0, -102.0, kind='base'), place('Rancho', 20.1, -102.0, [7, 8]),
              place('Lejos', 20.3, -102.0, [9])]
    day = date(2026, 11, 3)

    def month(self, stops, invoices=(), tasks=()):
        return Month(self.day, self.day, {}, erp=FakeErp(invoices), tasks=list(tasks), places=self.places, stops=stops, km={})

    def test_rows_skip_sites_and_pauses_name_invoiced_clients_and_join_split_visits(self):
        m = self.month([stop('t1', 8, 0, 30, 20.0), stop('t1', 9, 0, 1, 20.2), stop('t1', 10, 0, 20, 20.1),
                        stop('t1', 10, 22, 10, 20.1001), stop('t1', 11, 0, 30, 20.25)],
                       invoices=[(8, self.day + timedelta(days=1), 500.0, 'B1', 1)])
        rows = m.visit_rows(self.day, 't1')
        self.assertEqual([(r['arrive'].hour, r['cids']) for r in rows], [(10, [8]), (11, [])])  # office, 1-min pause gone
        self.assertEqual(rows[0]['leave'].minute, 32)   # the 10:22 stop at the same client is the same visit
        self.assertEqual((rows[0]['sale'], rows[0]['folios']), (500.0, 'B1'))
        self.assertIn('mismo lugar: 2 clientes', rows[0]['obs'])
        self.assertIn('Sin cliente', rows[1]['obs'])

    def test_salesman_truck_is_the_one_his_invoices_point_to(self):
        m = self.month([stop('t1', 10, 0, 20, 20.1), stop('t2', 10, 0, 20, 20.3), stop('t2', 12, 0, 20, 20.1)],
                       invoices=[(9, self.day, 100.0, 'B2', 1)])
        forms, route = m.routes()
        self.assertEqual(route, {('ZONA 1', self.day): 't2'})
        self.assertEqual(set(forms), {(self.day, 't1'), (self.day, 't2')})

    def test_crew_took_another_truck_when_its_own_visited_no_calendar_client(self):
        task = {'start': self.day, 'end': self.day, 'title': 'Tapetes', 'cids': [9], 'state': 'Listo'}
        m = self.month([stop('crew', 9, 0, 30, 20.0), stop('t2', 11, 0, 60, 20.3)], tasks=[task])
        self.assertEqual(m.crew_units(self.day), {'crew', 't2'})
        self.assertEqual(m.routes()[0], {})  # the crew's trucks are not sales routes
        m = self.month([stop('crew', 11, 0, 60, 20.3), stop('t2', 11, 0, 60, 20.3)], tasks=[task])
        self.assertEqual(m.crew_units(self.day), {'crew'})

    def test_service_invoices_keep_labor_and_drop_parts_under_the_generic_code(self):
        lines = [(1, 7, self.day, 900.0, 'B', 1, 5, '0000', 'BOMBA 2 HP'),   # the SERVICIOS agent: always a service
                 (2, 8, self.day, 300.0, '', 2, 2, '0000', 'SOPORTE'),        # a zone selling a part: not a service
                 (3, 8, self.day, 400.0, '', 3, 2, '0000', ''),               # no description: labor
                 (4, 9, self.day, 999.0, '', 4, 1, '0004', '')]
        found = service_invoices(lines)
        self.assertEqual([(x['folio'], x['concept']) for x in found],
                         [('B1', ['BOMBA 2 HP']), ('3', ['SERVICIO']), ('4', ['SERVICIO DE EMERGENCIA'])])

    def test_workbook_has_every_sheet_and_lists_unknown_stops_as_pending(self):
        m = self.month([stop('t1', 10, 0, 20, 20.1), stop('t1', 11, 0, 30, 20.25)],
                       invoices=[(7, self.day, 100.0, 'B3', 1)])
        wb = build_workbook(m)
        self.assertEqual(wb.sheetnames, ['PENDIENTES', 'ZONA 1', 'ZONA 2', 'SERVICIOS', 'OTRAS UNIDADES'])
        self.assertEqual(wb['PENDIENTES'].max_row, 3)  # title, header, the 11:00 stop
        self.assertIn('ANA', [c.value for c in wb['ZONA 1'][4]])

    def test_town_names_once_when_city_and_municipality_match(self):
        self.assertEqual(town('Valle de Juarez', 'VALLE DE JUÁREZ'), 'VALLE DE JUAREZ')
        self.assertEqual(town('Cerro Gordo', 'Tepatitlán de Morelos'), 'CERRO GORDO - TEPATITLÁN DE MORELOS')
        self.assertEqual(town(None, ' '), '')

    def test_calendar_job_without_a_stop_is_guessed_on_the_stop_nothing_else_explains(self):
        def row(minutes, found=None, cids=()):
            arrive = datetime(2026, 11, 14, 10, tzinfo=LOCAL_TZ)
            return {'found': found, 'cids': list(cids), 'arrive': arrive, 'leave': arrive + timedelta(minutes=minutes)}
        farm = {'kind': 'client', 'place': place('Rancho', 0, 0, [8]), 'meters': 5}
        rows = [row(90, farm, [8]), row(64), row(5)]
        job = {'title': 'Calibrar ventilador', 'cids': [9]}
        guesses = calendar_guesses([job], rows, [job], invoiced=lambda r: [])
        self.assertEqual(guesses, {id(rows[1]): job})       # the unknown stop beats a client's place; 5 min is too short
        self.assertEqual(calendar_guesses([job], rows[:1], [job], invoiced=lambda r: []), {id(rows[0]): job})
        self.assertEqual(calendar_guesses([job], rows[:1], [job], invoiced=lambda r: ['factura']), {})

    def test_calendar_job_done_by_another_truck_says_which(self):
        task = {'start': self.day, 'end': self.day, 'title': 'Tapetes', 'cids': [9], 'state': 'Listo'}
        other = {'start': self.day, 'end': self.day, 'title': 'Bomba', 'cids': [7], 'state': 'Listo'}
        m = self.month([stop('crew', 9, 0, 60, 20.1), stop('t2', 11, 0, 30, 20.3)], tasks=[task, other])
        wb = build_workbook(m)
        notes = [r[11] for r in wb['SERVICIOS'].iter_rows(values_only=True) if r[0] is None and r[7] == 'Tapetes']
        self.assertEqual(notes, ['En el calendario, pasó otra unidad: t2 11:00 (Listo)'])

    def test_same_client_twice_in_a_day_shows_the_sale_once(self):
        m = self.month([stop('t1', 10, 0, 10, 20.1), stop('t1', 10, 40, 30, 20.1001)],
                       invoices=[(7, self.day, 100.0, 'B4', 1)])
        rows = m.visit_rows(self.day, 't1')
        self.assertEqual([(r['sale'], r['folios']) for r in rows], [(100.0, 'B4'), (None, '')])
        self.assertIn('venta en la parada anterior', rows[1]['obs'])

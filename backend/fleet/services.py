"""Fleet GPS log: pulls each vehicle's trips from Zeek GPS and writes them to
Notion (a daily log database plus one card per vehicle holding its odometer).

Nothing here touches the ERP or the local database: Zeek is read, Notion is the
store. All credentials and ids come from settings (backend/.env), since the
repo is public."""

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from django.conf import settings

# Zeek reports in fixed UTC-6 (Mexico has had no DST since 2022).
LOCAL_TZ = timezone(timedelta(hours=-6))
ZEEK_URL = 'https://auto.zeekgps.com/ZeekApiJS/CMovilApi3WS.asmx/Historial_X_Viajes_2019UTC'
NOTION_URL = 'https://api.notion.com/v1'
MONTHLY_TITLE_PREFIX = 'Reporte Mensual - '
NOTION_MAX_CHILDREN = 100   # Notion rejects more blocks than this in one create
MAPS_MAX_STOPS = 20         # Google Maps directions links stop working past ~20 points


def _http(method, url, headers, body=None):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode('utf-8')


def notion(method, path, payload=None):
    headers = {
        'Authorization': f'Bearer {settings.NOTION_TOKEN}',
        'Content-Type': 'application/json',
        'Notion-Version': '2022-06-28',
    }
    body = json.dumps(payload).encode() if payload is not None else None
    return json.loads(_http(method, f'{NOTION_URL}/{path}', headers, body))


def notion_query(database_id, filter_):
    """All pages matching the filter; Notion pages results 100 at a time."""
    results, cursor = [], None
    while True:
        payload = {'filter': filter_, **({'start_cursor': cursor} if cursor else {})}
        data = notion('POST', f'databases/{database_id}/query', payload)
        results += data['results']
        if not data.get('has_more'):
            return results
        cursor = data['next_cursor']


def page_title(page):
    title = next(p for p in page['properties'].values() if p['type'] == 'title')['title']
    return ''.join(t['plain_text'] for t in title)


# --- Zeek ---------------------------------------------------------------------------------

def fetch_zeek_trips(imei, start_local, end_local):
    fmt = '%m/%d/%Y %H:%M:%S'
    form = {
        'unidadES': '',
        'unidad': imei,
        'token': settings.ZEEK_TOKEN,
        'cliente': settings.ZEEK_CLIENT,
        'licencia': settings.ZEEK_LICENSE,
        'fechaini': start_local.astimezone(timezone.utc).strftime(fmt),
        'fechafin': end_local.astimezone(timezone.utc).strftime(fmt),
        'utcOffset': '6',
        'app': 'ZMA',
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'Mozilla/5.0'}
    return parse_zeek_trips(_http('POST', ZEEK_URL, headers, urllib.parse.urlencode(form).encode()))


def parse_zeek_trips(text):
    """The JSON array comes wrapped in an XML envelope. Returns trips oldest first, only
    those with at least one GPS point."""
    start, end = text.find('['), text.rfind(']') + 1
    if start == -1 or end == 0:
        raise ValueError('Zeek response has no JSON array')
    trips = json.loads(text[start:end])
    trips.reverse()
    return [t for t in trips if t.get('listaUbicaciones')]


def zeek_coord(raw):
    """Zeek sends degrees and decimal minutes packed as DDMM.mmm * 1000 (e.g. 2053123 is
    20 deg 53.123 min); returns decimal degrees."""
    absolute = abs(raw) / 100000
    degrees = int(absolute)
    decimal = degrees + (absolute - degrees) * 100 / 60
    return decimal if raw >= 0 else -decimal


def zeek_time(raw):
    """'/Date(1696000000000)/' or '/Date(1696000000000-0600)/' -> local datetime."""
    return datetime.fromtimestamp(int(re.search(r'\d+', raw).group()) / 1000, tz=LOCAL_TZ)


def summarize_day(trips):
    """Daily km, a Google Maps route link and one Notion callout per trip."""
    first, last = trips[0]['listaUbicaciones'][0], trips[-1]['listaUbicaciones'][-1]
    km = round((int(last['odo']) - int(first['odo'])) / 1000, 2)

    points = [f"{zeek_coord(first['Latitud'])},{zeek_coord(first['Longitud'])}"]
    blocks = []
    for trip in trips:
        start, end = trip['listaUbicaciones'][0], trip['listaUbicaciones'][-1]
        lat, lon = zeek_coord(end['Latitud']), zeek_coord(end['Longitud'])
        points.append(f'{lat},{lon}')
        blocks.append({
            'object': 'block',
            'type': 'callout',
            'callout': {
                'icon': {'emoji': '📍'},
                'color': 'gray_background',
                'rich_text': [
                    {'type': 'text', 'text': {'content': (
                        f"🟢 {zeek_time(start['Fecha']):%I:%M %p}  ➔  🔴 {zeek_time(end['Fecha']):%I:%M %p}\nDestino: "
                    )}},
                    {'type': 'text', 'text': {
                        'content': end.get('ng') or 'Ver ubicación exacta en mapa',
                        'link': {'url': f'https://www.google.com/maps?q={lat},{lon}'},
                    }},
                    {'type': 'text', 'text': {'content': (
                        f"\n⏱️ {trip.get('recorrido', '0 m')} recorridos en {trip.get('tiempo', '0 min')}"
                    )}},
                ],
            },
        })

    route = 'https://www.google.com/maps/dir/' + '/'.join(points[:MAPS_MAX_STOPS])
    return km, route, blocks[:NOTION_MAX_CHILDREN]


def sync_day(day, log):
    """Writes one log entry per vehicle that moved on `day` and adds its km to the vehicle
    card's odometer. Skips vehicles already logged for that day, so re-running is safe."""
    start = datetime(day.year, day.month, day.day, tzinfo=LOCAL_TZ)
    end = start + timedelta(hours=23, minutes=59, seconds=59)

    for imei, card_id in settings.ZEEK_FLEET.items():
        card = notion('GET', f'pages/{card_id}')
        name = page_title(card)
        already = notion_query(settings.NOTION_FLEET_LOG_DB, {'and': [
            {'property': 'Fecha', 'date': {'equals': day.isoformat()}},
            {'property': 'Vehículo', 'title': {'equals': name}},
        ]})
        if already:
            log(f'[{name}] ya registrado el {day}, se omite.')
            continue

        try:
            trips = fetch_zeek_trips(imei, start, end)
        except (OSError, ValueError) as e:
            log(f'[{name}] error leyendo Zeek: {e}')
            continue
        if not trips:
            log(f'[{name}] sin viajes el {day}.')
            continue

        km, route, blocks = summarize_day(trips)
        odometer = round((card['properties']['Kilometraje']['number'] or 0) + km, 2)
        # Log entry first: if it fails the odometer stays untouched and a re-run fixes both.
        notion('POST', 'pages', {
            'parent': {'database_id': settings.NOTION_FLEET_LOG_DB},
            'properties': {
                'Vehículo': {'title': [{'text': {'content': name}}]},
                'Recorrido Diario': {'number': km},
                'Odómetro Total': {'number': odometer},
                'Ruta': {'url': route},
                'Fecha': {'date': {'start': day.isoformat()}},
            },
            'children': blocks,
        })
        notion('PATCH', f'pages/{card_id}', {'properties': {'Kilometraje': {'number': odometer}}})
        log(f'[{name}] {km} km, odómetro {odometer} km.')


# --- Monthly close ------------------------------------------------------------------------

def summarize_month(pages):
    """Groups daily log pages by vehicle:
    {name: {'km', 'odometer', 'days': [(date, km, route)], 'page_ids': [...]}}."""
    summary = {}
    for page in pages:
        props = page['properties']
        name = page_title(page)
        km = props['Recorrido Diario']['number'] or 0
        vehicle = summary.setdefault(name, {'km': 0, 'odometer': 0, 'days': [], 'page_ids': []})
        vehicle['km'] += km
        vehicle['odometer'] = max(vehicle['odometer'], props['Odómetro Total']['number'] or 0)
        vehicle['days'].append(((props['Fecha']['date'] or {}).get('start', ''), km, props['Ruta']['url']))
        vehicle['page_ids'].append(page['id'])
    for vehicle in summary.values():
        vehicle['km'] = round(vehicle['km'], 2)
        vehicle['days'].sort()
    return summary


def close_month(first_day, last_day, log):
    """One 'Reporte Mensual' entry per vehicle in the log database, spanning the month, then
    archives that vehicle's daily entries (the team's choice, to stay within Notion's limits;
    archived pages go to Notion's trash, which empties after 30 days). A vehicle whose monthly
    entry already exists is not summarized again, only its leftover daily entries archived, so
    re-running after a failure is safe."""
    monthly = notion_query(settings.NOTION_FLEET_LOG_DB, {'and': [
        {'property': 'Fecha', 'date': {'equals': first_day.isoformat()}},
        {'property': 'Vehículo', 'title': {'starts_with': MONTHLY_TITLE_PREFIX}},
    ]})
    closed = {page_title(p).removeprefix(MONTHLY_TITLE_PREFIX) for p in monthly}

    pages = notion_query(settings.NOTION_FLEET_LOG_DB, {'and': [
        {'property': 'Fecha', 'date': {'on_or_after': first_day.isoformat()}},
        {'property': 'Fecha', 'date': {'on_or_before': last_day.isoformat()}},
        {'property': 'Vehículo', 'title': {'does_not_contain': MONTHLY_TITLE_PREFIX.strip(' -')}},
    ]})
    if not pages:
        log('No hay registros diarios en ese mes.')
        return

    for name, vehicle in summarize_month(pages).items():
        if name in closed:
            log(f'[{name}] ya tiene reporte mensual.')
        else:
            create_monthly_entry(name, vehicle, first_day, last_day)
            log(f"[{name}] {vehicle['km']} km en el mes.")
        # Only after the monthly entry exists, so a failed create never loses the daily detail.
        for page_id in vehicle['page_ids']:
            notion('PATCH', f'pages/{page_id}', {'archived': True})
        log(f"[{name}] {len(vehicle['page_ids'])} registros diarios archivados.")


def create_monthly_entry(name, vehicle, first_day, last_day):
    days = [{
        'object': 'block',
        'type': 'bulleted_list_item',
        'bulleted_list_item': {'rich_text': [
            {'type': 'text', 'text': {'content': f'📅 {day} | Recorrido: {km} km | '}},
            {'type': 'text', 'text': {'content': 'Ver mapa de ruta', 'link': {'url': route}}}
            if route else {'type': 'text', 'text': {'content': 'Sin mapa'}},
        ]},
    } for day, km, route in vehicle['days']]
    notion('POST', 'pages', {
        'parent': {'database_id': settings.NOTION_FLEET_LOG_DB},
        'properties': {
            'Vehículo': {'title': [{'text': {'content': MONTHLY_TITLE_PREFIX + name}}]},
            'Recorrido Diario': {'number': vehicle['km']},
            'Odómetro Total': {'number': vehicle['odometer']},
            'Fecha': {'date': {'start': first_day.isoformat(), 'end': last_day.isoformat()}},
        },
        'children': [
            {'object': 'block', 'type': 'heading_3', 'heading_3': {'rich_text': [
                {'type': 'text', 'text': {'content': f'Desglose de viajes {first_day:%Y-%m}'}},
            ]}},
            {'object': 'block', 'type': 'divider', 'divider': {}},
        ] + days[:NOTION_MAX_CHILDREN - 2],
    })

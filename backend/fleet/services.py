"""Fleet GPS log jobs: each vehicle's day from Zeek goes to the local database (km and stops, store_km)
and to the Notion log (one page per vehicle per day plus its odometer card, sync_day), both from the same
legs (timeline.py); the monthly close sums Notion's daily pages. Zeek keeps only about six days, so the
local tables are the long-term record. Nothing here touches the ERP except reading client names.

The modules: zeek.py (API and parsing), timeline.py (trips -> legs and stops), matching.py (what a stop
was, from the saved places), notion.py (API, callouts and reading them back). All credentials and ids
come from settings (backend/.env), since the repo is public."""

from datetime import datetime, timedelta

from django.conf import settings

from .matching import StopMatcher, client_names
from .models import VehicleDayKm, VehicleStop
from .notion import (NOTION_COORDS, NOTION_MAX_CHILDREN, children, day_blocks, notion, notion_query, notion_stops, page_title,
                     plain, renamed, stop_name)
from .timeline import legs, stops
from .zeek import LOCAL_TZ, day_km, fetch_zeek_trips

MONTHLY_TITLE_PREFIX = 'Reporte Mensual - '


def day_trips(imei, day):
    start = datetime(day.year, day.month, day.day, tzinfo=LOCAL_TZ)
    return fetch_zeek_trips(imei, start, start + timedelta(hours=23, minutes=59, seconds=59))


def namer():
    """Names stops for the Notion log: the saved places as they are now, and their clients' ERP names."""
    matcher = StopMatcher()
    return matcher, client_names({c for p in matcher.clients for c in p.client_ids})


def log_page(day, name):
    pages = notion_query(settings.NOTION_FLEET_LOG_DB, {'and': [
        {'property': 'Fecha', 'date': {'equals': day.isoformat()}},
        {'property': 'Vehículo', 'title': {'equals': name}},
    ]})
    return pages[0] if pages else None


def sync_day(day, log):
    """Writes one log entry per vehicle that moved on `day` and adds its km to the vehicle
    card's odometer. Skips vehicles already logged for that day, so re-running is safe."""
    matcher, names = namer()
    for imei, card_id in settings.ZEEK_FLEET.items():
        card = notion('GET', f'pages/{card_id}')
        name = page_title(card)
        if log_page(day, name):
            log(f'[{name}] ya registrado el {day}, se omite.')
            continue
        try:
            trips = day_trips(imei, day)
        except (OSError, ValueError) as e:
            log(f'[{name}] error leyendo Zeek: {e}')
            continue
        if not trips:
            log(f'[{name}] sin viajes el {day}.')
            continue

        km = day_km(trips)
        blocks, route = day_blocks(legs(trips), matcher, names)
        odometer = round((card['properties']['Kilometraje']['number'] or 0) + km, 2)
        # Log entry first: if it fails the odometer stays untouched and a re-run fixes both.
        notion('POST', 'pages', {
            'parent': {'database_id': settings.NOTION_FLEET_LOG_DB},
            'properties': {
                'Vehículo': {'title': [{'text': {'content': name}}]},
                'Recorrido Diario': {'number': km},
                'Kilometraje Total': {'number': odometer},
                'Ruta': {'url': route},
                'Fecha': {'date': {'start': day.isoformat()}},
            },
            'children': blocks,
        })
        notion('PATCH', f'pages/{card_id}', {'properties': {'Kilometraje': {'number': odometer}}})
        log(f'[{name}] {km} km, odómetro {odometer} km.')


def rewrite_day(day, only, log):
    """Rewrites the callouts and route link of `day`'s log pages from Zeek (which keeps ~6 days), for pages
    written before engine-on stops and names existed. Km and odometers are left alone. `only`: one vehicle
    name, or None for all."""
    matcher, names = namer()
    for imei, card_id in settings.ZEEK_FLEET.items():
        name = page_title(notion('GET', f'pages/{card_id}'))
        if only and name.lower() != only.lower():
            continue
        page = log_page(day, name)
        if not page:
            continue
        trips = day_trips(imei, day)
        if not trips:
            log(f'[{name}] Zeek ya no tiene {day}; la página se deja como está.')
            continue
        blocks, route = day_blocks(legs(trips), matcher, names)
        old = [b for b in children(page['id']) if b['type'] == 'callout']
        # New callouts first: if this fails halfway the page has both, never neither.
        notion('PATCH', f"blocks/{page['id']}/children", {'children': blocks})
        for block in old:
            notion('DELETE', f"blocks/{block['id']}")
        notion('PATCH', f"pages/{page['id']}", {'properties': {'Ruta': {'url': route}}})
        log(f'[{name}] {day}: {len(blocks)} tramos reescritos.')


def refresh_names(first_day, last_day, log):
    """Re-names the stops on the daily log pages still in Notion, from the saved places as they are now
    (a pin fixed, a spot identified after the page was written). Only the name line changes."""
    matcher, names = namer()
    for page in daily_pages(first_day, last_day):
        changed = 0
        for block in children(page['id']):
            rich = block.get('callout', {}).get('rich_text', [])
            coords = next((NOTION_COORDS.search(t['text']['link']['url']) for t in rich if t['text'].get('link')), None)
            if not coords:
                continue
            new = renamed(rich, stop_name(matcher.match(float(coords[1]), float(coords[2])), names))
            if new != plain(rich):
                notion('PATCH', f"blocks/{block['id']}", {'callout': {'rich_text': new}})
                changed += 1
        if changed:
            log(f"[{page_title(page)}] {page['properties']['Fecha']['date']['start']}: {changed} paradas renombradas.")


def daily_pages(first_day, last_day):
    return notion_query(settings.NOTION_FLEET_LOG_DB, {'and': [
        {'property': 'Fecha', 'date': {'on_or_after': first_day.isoformat()}},
        {'property': 'Fecha', 'date': {'on_or_before': last_day.isoformat()}},
        {'property': 'Vehículo', 'title': {'does_not_contain': MONTHLY_TITLE_PREFIX.strip(' -')}},
    ]})


def save_stops(imei, day, day_stops, source):
    VehicleStop.objects.filter(imei=imei, day=day).delete()
    VehicleStop.objects.bulk_create(VehicleStop(imei=imei, day=day, source=source, **s) for s in day_stops)


def store_km(first_day, last_day, log):
    """Saves every unit's km and stops for each day in the range, 0 km when it didn't move.
    Re-running is safe: a day is overwritten only with at least as many km as already stored, since
    Zeek sometimes answers with fewer or no trips for a unit that did move (a late upload, or a day
    already trimming out of its window). A unit Zeek fails to answer for is skipped and left without
    a row for that day, so the gap is visible."""
    day = first_day
    while day <= last_day:
        for n, imei in enumerate(settings.ZEEK_FLEET, 1):
            try:
                trips = day_trips(imei, day)
            except (OSError, ValueError) as e:
                log(f'[unidad {n}] {day}: error leyendo Zeek: {e}')
                continue
            km = day_km(trips) if trips else 0
            stored = VehicleDayKm.objects.filter(imei=imei, day=day).values_list('km', flat=True).first()
            if stored is not None and km < float(stored):  # day_km is a float rounded to 2 places
                log(f'[unidad {n}] {day}: Zeek da {km} km, menos de los {stored} guardados; se conservan')
                continue
            VehicleDayKm.objects.update_or_create(imei=imei, day=day, defaults={'km': km})
            day_stops = stops(legs(trips))
            save_stops(imei, day, day_stops, 'zeek')
            idle = sum(s['engine_on'] for s in day_stops)
            log(f'[unidad {n}] {day}: {km} km, {len(day_stops)} paradas ({idle} con motor encendido)')
        day += timedelta(days=1)


def vehicle_imeis():
    """{vehicle name, lowercased: IMEI}, from the Notion cards. By name in any case, so log pages written
    before a card was renamed ('Isuzu Bodega' -> 'Isuzu bodega') still match."""
    return {page_title(notion('GET', f'pages/{card}')).lower(): imei for imei, card in settings.ZEEK_FLEET.items()}


def rescue_notion_stops(log):
    """Stops and km for the days still in Notion's daily log but no longer in Zeek. Days already stored
    from Zeek are left alone. close_month runs it before archiving the pages."""
    imeis = vehicle_imeis()
    pages = notion_query(settings.NOTION_FLEET_LOG_DB, {'and': [
        {'property': 'Fecha', 'date': {'is_not_empty': True}},
        {'property': 'Vehículo', 'title': {'does_not_contain': MONTHLY_TITLE_PREFIX.strip(' -')}},
    ]})
    for page in pages:
        name, day = page_title(page), datetime.fromisoformat(page['properties']['Fecha']['date']['start']).date()
        imei = imeis.get(name.lower())
        if not imei or VehicleStop.objects.filter(imei=imei, day=day, source='zeek').exists():
            continue
        day_stops = notion_stops(day, children(page['id']))
        save_stops(imei, day, day_stops, 'notion')
        km = page['properties'].get('Recorrido Diario', {}).get('number')
        if km is not None:
            VehicleDayKm.objects.update_or_create(imei=imei, day=day, defaults={'km': km})
        log(f'[{name}] {day}: {len(day_stops)} paradas, {km} km desde Notion')


# --- Monthly close ------------------------------------------------------------------------

def summarize_month(pages):
    """Groups daily log pages by vehicle:
    {name: {'km', 'odometer', 'days': [(date, km, route)], 'pages': [(page id, date)]}}."""
    summary = {}
    for page in pages:
        props = page['properties']
        name = page_title(page)
        km = props['Recorrido Diario']['number'] or 0
        day = (props['Fecha']['date'] or {}).get('start', '')
        vehicle = summary.setdefault(name, {'km': 0, 'odometer': 0, 'days': [], 'pages': []})
        vehicle['km'] += km
        vehicle['odometer'] = max(vehicle['odometer'], props['Kilometraje Total']['number'] or 0)
        vehicle['days'].append((day, km, props['Ruta']['url']))
        vehicle['pages'].append((page['id'], day))
    for vehicle in summary.values():
        vehicle['km'] = round(vehicle['km'], 2)
        vehicle['days'].sort()
    return summary


def close_month(first_day, last_day, log):
    """One 'Reporte Mensual' entry per vehicle in the log database, spanning the month, then
    archives that vehicle's daily entries (the team's choice, to stay within Notion's limits;
    archived pages go to Notion's trash, which empties after 30 days). A vehicle whose monthly
    entry already exists is not summarized again, only its leftover daily entries archived, so
    re-running after a failure is safe. Nothing is lost to the archive: every daily page's km and stops
    are first copied into the local database (rescue_notion_stops), and a page is archived only once
    its vehicle has that day stored locally."""
    monthly = notion_query(settings.NOTION_FLEET_LOG_DB, {'and': [
        {'property': 'Fecha', 'date': {'equals': first_day.isoformat()}},
        {'property': 'Vehículo', 'title': {'starts_with': MONTHLY_TITLE_PREFIX}},
    ]})
    closed = {page_title(p).removeprefix(MONTHLY_TITLE_PREFIX) for p in monthly}

    pages = daily_pages(first_day, last_day)
    if not pages:
        log('No hay registros diarios en ese mes.')
        return

    rescue_notion_stops(log)
    imeis = vehicle_imeis()
    for name, vehicle in summarize_month(pages).items():
        if name in closed:
            log(f'[{name}] ya tiene reporte mensual.')
        else:
            create_monthly_entry(name, vehicle, first_day, last_day)
            log(f"[{name}] {vehicle['km']} km en el mes.")
        # Only after the monthly entry exists, so a failed create never loses the daily detail.
        imei = imeis.get(name.lower())
        stored = {d.isoformat() for d in VehicleDayKm.objects.filter(
            imei=imei, day__range=(first_day, last_day)).values_list('day', flat=True)} if imei else set()
        kept = [day for _, day in vehicle['pages'] if day not in stored]
        for page_id, day in vehicle['pages']:
            if day in stored:
                notion('PATCH', f'pages/{page_id}', {'archived': True})
        log(f"[{name}] {len(vehicle['pages']) - len(kept)} registros diarios archivados.")
        if kept:
            log(f"[{name}] NO se archivan {', '.join(sorted(kept))}: ese día no está guardado en la base local.")


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
            'Kilometraje Total': {'number': vehicle['odometer']},
            'Fecha': {'date': {'start': first_day.isoformat(), 'end': last_day.isoformat()}},
        },
        'children': [
            {'object': 'block', 'type': 'heading_3', 'heading_3': {'rich_text': [
                {'type': 'text', 'text': {'content': f'Desglose de viajes {first_day:%Y-%m}'}},
            ]}},
            {'object': 'block', 'type': 'divider', 'divider': {}},
        ] + days[:NOTION_MAX_CHILDREN - 2],
    })

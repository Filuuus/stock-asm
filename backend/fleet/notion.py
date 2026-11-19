"""The Notion fleet log: API calls, the daily page's callouts and reading them back.

Each callout is one leg of driving (timeline.py), marked like a traffic light: 🟢 leaving a parked spot,
🟡 an engine-on stop (ending one leg, starting the next), 🔴 the ignition off. Under the destination link,
the stop's name from the saved places (matching.py): 👤 clients, 📌 a known spot, 🏢 a company site."""

import json
import re
from datetime import datetime

from django.conf import settings

from .zeek import LOCAL_TZ, http

NOTION_URL = 'https://api.notion.com/v1'
NOTION_MAX_CHILDREN = 100   # Notion rejects more blocks than this in one create
MAPS_MAX_STOPS = 20         # Google Maps directions links stop working past ~20 points
START = {'parked': '🟢', 'idle': '🟡'}
END = {'idle': '🟡', 'parked': '🔴'}
NAME_MARKS = ('👤', '📌', '🏢')
NOTION_TRIP = re.compile(r'([🟢🟡])\s*(\d{1,2}:\d{2} [AP]M)\s*➔\s*([🟡🔴])\s*(\d{1,2}:\d{2} [AP]M)')
NOTION_COORDS = re.compile(r'q=(-?[\d.]+)(?:%2C|,)(-?[\d.]+)')


def notion(method, path, payload=None):
    headers = {
        'Authorization': f'Bearer {settings.NOTION_TOKEN}',
        'Content-Type': 'application/json',
        'Notion-Version': '2022-06-28',
    }
    body = json.dumps(payload).encode() if payload is not None else None
    return json.loads(http(method, f'{NOTION_URL}/{path}', headers, body))


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


def children(block_id):
    found, cursor = [], None
    while True:
        data = notion('GET', f'blocks/{block_id}/children?page_size=100' + (f'&start_cursor={cursor}' if cursor else ''))
        found += data['results']
        if not data.get('has_more'):
            return found
        cursor = data['next_cursor']


def page_title(page):
    title = next(p for p in page['properties'].values() if p['type'] == 'title')['title']
    return ''.join(t['plain_text'] for t in title)


def _text(content, url=None):
    return {'type': 'text', 'text': {'content': content, **({'link': {'url': url}} if url else {})}}


def stop_name(found, names):
    """The line naming a stop, or '' when it's unknown (or a spot looked at and left unnamed)."""
    if not found:
        return ''
    place = found['place']
    if found['kind'] == 'client':
        listed = ' / '.join(names[c] for c in place.client_ids if c in names)
        return f"\n👤 {listed} (~{found['meters']} m)" if listed else ''
    if found['kind'] == 'base':
        return f'\n🏢 {place.name}'
    if place.personal:
        return '\n📌 Parada personal'
    return f'\n📌 {place.name}' if place.name else ''


def leg_callout(leg, name_line):
    lat, lng = leg['lat'], leg['lng']
    minutes = round((leg['end'] - leg['start']).total_seconds() / 60)
    footer = f"\n⏱️ {leg['km']} km en {minutes} min" if leg['km'] is not None else f'\n⏱️ {minutes} min'
    if leg['end_kind'] == 'idle' and leg['leave']:
        footer += f" · motor encendido {round((leg['leave'] - leg['end']).total_seconds() / 60)} min"
    return {
        'object': 'block',
        'type': 'callout',
        'callout': {
            'icon': {'emoji': '📍'},
            'color': 'gray_background',
            'rich_text': [
                _text(f"{START[leg['start_kind']]} {leg['start']:%I:%M %p}  ➔  {END[leg['end_kind']]} {leg['end']:%I:%M %p}"
                      '\nDestino: '),
                _text(leg['place'] or 'Ver ubicación exacta en mapa', f'https://www.google.com/maps?q={lat},{lng}'),
                *([_text(name_line)] if name_line else []),
                _text(footer),
            ],
        },
    }


def day_blocks(day_legs, matcher, names):
    """One callout per leg (at most NOTION_MAX_CHILDREN) and the day's Google Maps route link, which
    goes through the parked stops only: engine-on stops would use up its 20 points."""
    blocks = [leg_callout(leg, stop_name(matcher.match(leg['lat'], leg['lng']), names)) for leg in day_legs]
    points = [f"{day_legs[0]['from_lat']},{day_legs[0]['from_lng']}"] if day_legs else []
    points += [f"{leg['lat']},{leg['lng']}" for leg in day_legs if leg['end_kind'] == 'parked']
    route = 'https://www.google.com/maps/dir/' + '/'.join(points[:MAPS_MAX_STOPS])
    return blocks[:NOTION_MAX_CHILDREN], route


def notion_stops(day, blocks):
    """The stops of one daily log page, from its callouts: where each ended (🟡 engine on, 🔴 off),
    until the next one starts. Pages from before the 🟡 marks read the same way."""
    legs = []
    for block in blocks:
        rich = block.get('callout', {}).get('rich_text', [])
        times = NOTION_TRIP.search(''.join(t['text']['content'] for t in rich))
        coords = next((NOTION_COORDS.search(t['text']['link']['url']) for t in rich if t['text'].get('link')), None)
        if times and coords:
            at = lambda hhmm: datetime.combine(day, datetime.strptime(hhmm, '%I:%M %p').time(), LOCAL_TZ)
            legs.append((at(times[2]), at(times[4]), times[3] == '🟡', float(coords[1]), float(coords[2])))
    return [{'arrive': end, 'leave': legs[i + 1][0] if i + 1 < len(legs) else None, 'lat': lat, 'lng': lng,
             'engine_on': idle} for i, (_, end, idle, lat, lng) in enumerate(legs)]


def plain(rich_text):
    """Rich text as Notion returns it, cut down to what we write (content and link)."""
    return [_text(t['text']['content'], (t['text'].get('link') or {}).get('url')) for t in rich_text]


def renamed(rich_text, name_line):
    """A callout's text with its name line replaced (or added, or dropped)."""
    plain_ = [t for t in plain(rich_text) if not t['text']['content'].lstrip('\n').startswith(NAME_MARKS)]
    at = next((i for i, t in enumerate(plain_) if t['text']['content'].startswith('\n⏱️')), len(plain_))
    return plain_[:at] + ([_text(name_line)] if name_line else []) + plain_[at:]

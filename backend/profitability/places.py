"""Google Maps Takeout parsing and matching saved places to ERP clients by name."""
import csv
import json
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from math import cos, radians
from pathlib import Path

# Words that describe a place rather than name it ("Casa de ...", "Rancho ...", company suffixes).
STOPWORDS = {
    'de', 'del', 'la', 'las', 'los', 'el', 'y', 'e', 'casa', 'rancho', 'establo', 'oficina', 'engorda', 'borregos',
    'sa', 'cv', 'sc', 'rl', 'spr', 'pr', 's', 'r', 'l', 'c', 'v', 'sociedad', 'cooperativa', 'jr',
}
# Titles Maps gives to dropped pins; the client's name is then in the note.
PIN_TITLES = {'marcador', 'chincheta', 'pin colocado', 'unnamed road'}
SEARCH_COORDS = re.compile(r'/maps/search/(-?\d+\.\d+),\s*(-?\d+\.\d+)')
# A family farm can be several clients; more names than this means the name is too common to tell.
MAX_FAMILY = 3
DMS = re.compile(r'(\d+)°(\d+)\'([\d.]+)"([NS])\s+(\d+)°(\d+)\'([\d.]+)"([EW])')


def words(name):
    text = unicodedata.normalize('NFKD', name.lower()).encode('ascii', 'ignore').decode()
    return [t for t in re.findall(r'[a-z0-9]+', text) if t not in STOPWORDS and not t.isdigit()]


def tokens(name):
    return set(words(name))


def _same(a, b):
    # A typo is one letter off (Briceño/Briseño, Cortez/Cortés); two surnames that differ by more are different people.
    short = min(len(a), len(b))
    return a == b or (short >= 5 and abs(len(a) - len(b)) <= 1
                      and SequenceMatcher(None, a, b).ratio() >= (0.8 if short >= 6 else 0.85))


def _holds(client, want):
    """Whether the client's words hold every wanted word, a repeated one as often (Mora Mora)."""
    left = list(client)
    for w in want:
        hit = next((c for c in left if _same(w, c)), None)
        if hit is None:
            return False
        left.remove(hit)
    return True


def match_clients(name, clients, zone=None, client_zones=None):
    """The clients a place is: those whose name holds every word of `name` (allowing small typos).
    `clients`: (id, name) pairs; `client_zones`: clients invoiced lately -> the zone whose salesperson
    invoices them, None for office and service sales, which can be anywhere; `zone`: the zone whose
    territory the place is in. When several clients hold the words, those invoiced lately and not by the
    other zone win (a duplicate ERP record without sales loses to the real one), then the ones with exactly
    the name's words; up to MAX_FAMILY stay, since family farms are several clients. A single word must be
    5+ letters and belong to one such client only, so a bare first name or surname never matches."""
    want = words(name)
    if not want or (len(want) == 1 and len(want[0]) < 5):
        return []
    hits = [(cid, client) for cid, client in clients if _holds(words(client), want)]
    if len(hits) > 1 or len(want) == 1:
        client_zones = client_zones or {}
        preferred = [h for h in hits if h[0] in client_zones and (not zone or client_zones[h[0]] in (zone, None))]
        if preferred or len(want) == 1:
            hits = preferred
    if len(want) == 1 and len(hits) != 1:
        return []
    exact = [h for h in hits if len(words(h[1])) == len(want)]
    hits = exact or hits
    return [cid for cid, _ in hits] if len(hits) <= MAX_FAMILY else []


def territory(lat, lng, labeled, k=5):
    """The zone most of the k places nearest to (lat, lng) are in; `labeled`: (lat, lng, zone). ZONA1
    and ZONA2 never share territory (management, 2026-10-14), so neighbours tell whose a place is."""
    scale = cos(radians(lat))
    near = sorted(labeled, key=lambda p: (p[0] - lat) ** 2 + ((p[1] - lng) * scale) ** 2)[:k]
    return Counter(p[2] for p in near).most_common(1)[0][0] if near else None


def _coords(url, title):
    m = SEARCH_COORDS.search(url)
    if m:
        return float(m[1]), float(m[2])
    m = DMS.search(title)
    if m:
        lat = int(m[1]) + int(m[2]) / 60 + float(m[3]) / 3600
        lng = int(m[5]) + int(m[6]) / 60 + float(m[7]) / 3600
        return (-lat if m[4] == 'S' else lat), (-lng if m[8] == 'W' else lng)
    return None, None


def read_takeout(folder):
    """Every saved place under a Takeout folder: the Save/*.csv lists and Maps' labeled places.
    Yields dicts with url, name, list_name, lat, lng (None when the list only has a place link)."""
    folder = Path(folder)
    for path in sorted(folder.glob('Save/*.csv')):
        with open(path, encoding='utf-8') as f:
            for row in csv.DictReader(f):
                url, title, note = row['URL'], row['Título'].strip(), row['Nota'].strip()
                if '/maps/' not in url:
                    continue  # saved web pages and images
                generic = title.lower() in PIN_TITLES or DMS.search(title)
                name = note or ('' if generic else title)
                if not name:
                    continue
                lat, lng = _coords(url, title)
                yield {'url': url, 'name': ' '.join(name.split()), 'list_name': path.stem, 'lat': lat, 'lng': lng}
    labeled = folder / 'Maps' / 'Mis sitios etiquetados' / 'Sitios etiquetados.json'
    if labeled.exists():
        for feature in json.loads(labeled.read_text(encoding='utf-8'))['features']:
            lng, lat = feature['geometry']['coordinates']
            yield {'url': f'geo:{lat:.6f},{lng:.6f}', 'name': feature['properties']['name'], 'list_name': 'Etiquetados',
                   'lat': lat, 'lng': lng}

"""Google Maps Takeout parsing and matching saved places to ERP clients by name."""
import csv
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

# Words that describe a place rather than name it ("Casa de ...", "Rancho ...", company suffixes).
STOPWORDS = {
    'de', 'del', 'la', 'las', 'los', 'el', 'y', 'e', 'casa', 'rancho', 'establo', 'oficina', 'engorda', 'borregos',
    'sa', 'cv', 'sc', 'rl', 'spr', 'pr', 's', 'r', 'l', 'c', 'v', 'sociedad', 'cooperativa', 'jr',
}
# Titles Maps gives to dropped pins; the client's name is then in the note.
PIN_TITLES = {'marcador', 'chincheta', 'pin colocado', 'unnamed road'}
SEARCH_COORDS = re.compile(r'/maps/search/(-?\d+\.\d+),\s*(-?\d+\.\d+)')
DMS = re.compile(r'(\d+)°(\d+)\'([\d.]+)"([NS])\s+(\d+)°(\d+)\'([\d.]+)"([EW])')


def tokens(name):
    text = unicodedata.normalize('NFKD', name.lower()).encode('ascii', 'ignore').decode()
    return {t for t in re.findall(r'[a-z0-9]+', text) if t not in STOPWORDS and not t.isdigit()}


def _same(a, b):
    # A typo is one letter off (Briceño/Briseño); two surnames that differ by more are different people.
    return a == b or (min(len(a), len(b)) >= 5 and abs(len(a) - len(b)) <= 1 and SequenceMatcher(None, a, b).ratio() >= 0.85)


def match_client(name, clients):
    """The one client whose name holds every word of `name` (allowing small typos), or None when no
    client or more than one does. `clients`: (id, name) pairs. Needs two words, so a bare first name
    or surname never matches."""
    want = tokens(name)
    if len(want) < 2:
        return None
    hits = [cid for cid, client in clients if all(any(_same(w, c) for c in tokens(client)) for w in want)]
    return hits[0] if len(hits) == 1 else None


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

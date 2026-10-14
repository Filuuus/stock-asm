"""Google Maps Takeout parsing and matching saved places to ERP clients by name."""
import csv
import json
import re
import unicodedata
from collections import Counter
from functools import lru_cache
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
# A family farm can be several clients; more names than this means the name is too common to tell...
MAX_FAMILY = 3
# ...unless the place is named after the surnames they all end with ("Sierra Olmos").
MAX_SURNAME_FAMILY = 8
# A word in at most this many client names is distinctive enough to anchor a partial match.
RARE = 10
# Labels that are a street address, not a client ("Calle Hidalgo 57", "JAL 304").
STREET = re.compile(r'^\s*(calle|c\.|av\.?|avenida|blvd\.?|boulevard|carretera|privada|prol\.?|prolongaci[oó]n|jal)\b',
                    re.IGNORECASE)
# One place saved for several clients: "Fulano y Mengano", "Rancho X, Fulano", "Rancho X. Fulano".
SEPARATORS = re.compile(r',|;|\.\s+|\s+y/o\s+|\s+y\s+|\s+e\s+', re.IGNORECASE)
DMS = re.compile(r'(\d+)°(\d+)\'([\d.]+)"([NS])\s+(\d+)°(\d+)\'([\d.]+)"([EW])')


@lru_cache(maxsize=None)
def words(name):
    text = unicodedata.normalize('NFKD', name.lower()).encode('ascii', 'ignore').decode()
    return tuple(t for t in re.findall(r'[a-z0-9]+', text) if t not in STOPWORDS and not t.isdigit())


def _same(a, b):
    # A typo is one letter off (Briceño/Briseño, Cortez/Cortés); two surnames that differ by more are different people.
    short = min(len(a), len(b))
    return a == b or (short >= 5 and abs(len(a) - len(b)) <= 1
                      and SequenceMatcher(None, a, b).ratio() >= (0.8 if short >= 6 else 0.85))


def _common(a, b):
    """How many words of `a` find their own word in `b` (a repeated one as often: Mora Mora). The last word of
    `a` may be cut short, as Maps labels are ("Tello Rí")."""
    left, n = list(b), 0
    for i, w in enumerate(a):
        cut = i == len(a) - 1 and len(w) >= 4
        hit = next((c for c in left if _same(w, c) or (cut and c.startswith(w))), None)
        if hit is not None:
            left.remove(hit)
            n += 1
    return n


def _tier(want, client, df):
    """How well a client's words fit a place's: 0 the same name, 1 the place's words inside a longer client
    name, 2 the client's inside the place's (the place adds a ranch name: "Fulano Grulla"), 3 one word off on
    each side but sharing a distinctive word; None when they don't fit. A one-word fit must be a 5+ letter
    word, and inside a longer place name, a word no other client has."""
    m = _common(want, client)
    if m == 0:
        return None
    if m == len(want) == len(client):
        tier = 0
    elif m == len(want):
        tier = 1
    elif m == len(client):
        tier = 2
    elif m >= 2 and len(want) - m <= 1 and len(client) - m <= 1 and any(
            df[c] <= RARE for c in client if any(_same(w, c) for w in want)):
        return 3
    else:
        return None
    if m == 1 and (len(client[0] if tier == 2 else want[0]) < 5 or (tier == 2 and df[client[0]] > 1)):
        return None
    return tier


def _ends_with(client, want):
    return len(client) > len(want) and all(_same(w, c) for w, c in zip(want, client[-len(want):]))


def match_clients(name, clients, zone=None, client_zones=None):
    """The clients a place is. A name joining several ("Fulano y Mengano", "Rancho X, Fulano") is matched
    part by part. `clients`: (id, name) pairs; `client_zones`: clients invoiced lately -> the zone whose
    salesperson invoices them, None for office and service sales, which can be anywhere; `zone`: the zone
    whose territory the place is in."""
    if STREET.match(name):
        return []
    parts = [p for p in SEPARATORS.split(name) if words(p)]
    if len(parts) > 1:
        found = []
        for part in parts:
            found += [c for c in _match(part, clients, zone, client_zones or {}) if c not in found]
        if found:
            return found
    return _match(name, clients, zone, client_zones or {})


def _match(name, clients, zone, client_zones):
    """Clients in the best-fitting tier (see _tier). A place named after surnames several clients end with
    is that family's farm, so all of them (near a zone border the family beats the territory). Otherwise, of several clients,
    those invoiced lately and not by the other zone win (a duplicate ERP record without sales loses to the
    real one); up to MAX_FAMILY stay, since family farms are several clients."""
    want = words(name)
    if not want:
        return []
    df = Counter(w for _, client in clients for w in set(words(client)))
    tiers = {}
    for cid, client in clients:
        tier = _tier(want, words(client), df)
        if tier is not None:
            tiers.setdefault(tier, []).append((cid, words(client)))
    if not tiers:
        return []
    hits = tiers[min(tiers)]
    if len(want) >= 2:
        family = [cid for cid, client in hits if _ends_with(client, want)]
        if len(family) > 1:
            return family if len(family) <= MAX_SURNAME_FAMILY else []
    if len(hits) > 1:
        preferred = [h for h in hits if h[0] in client_zones and (not zone or client_zones[h[0]] in (zone, None))]
        hits = preferred or hits
    if len(want) == 1 and len(hits) > 1:
        return []  # a bare word several clients share ("México")
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

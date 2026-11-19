"""Reading trips from the Zeek GPS API. Credentials and unit ids come from settings (backend/.env)."""

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from django.conf import settings

# Zeek reports in fixed UTC-6 (Mexico has had no DST since 2022).
LOCAL_TZ = timezone(timedelta(hours=-6))
ZEEK_URL = 'https://auto.zeekgps.com/ZeekApiJS/CMovilApi3WS.asmx/Historial_X_Viajes_2019UTC'


def http(method, url, headers, body=None):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode('utf-8')


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
    return parse_zeek_trips(http('POST', ZEEK_URL, headers, urllib.parse.urlencode(form).encode()))


def fetch_day(imei, day):
    start = datetime(day.year, day.month, day.day, tzinfo=LOCAL_TZ)
    return fetch_zeek_trips(imei, start, start + timedelta(hours=23, minutes=59, seconds=59))


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


def day_km(trips):
    """Km between the day's first and last odometer reading (Zeek's odo is in meters)."""
    first, last = trips[0]['listaUbicaciones'][0], trips[-1]['listaUbicaciones'][-1]
    return round((int(last['odo']) - int(first['odo'])) / 1000, 2)

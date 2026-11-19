"""A vehicle's day as legs of driving between stops, built from its Zeek trips. Both the local database
(stops) and the Notion log (one callout per leg) are written from these legs, so they always agree.

Zeek ends a trip only when the ignition goes off, so a truck left running at a client leaves no trip end.
Inside each trip, a run of points at walking speed or less (IDLE_SPEED), within IDLE_RADIUS_M of the run's
first point and lasting IDLE_MIN or more, is such an engine-on stop: it ends one leg and starts the next.
A run at the very end of a trip is the truck idling before it was turned off, so the stop starts when it
stopped moving; a run at the very start is it warming up, and the departure stays at ignition on."""

import math
from datetime import timedelta

from .zeek import zeek_coord, zeek_time

IDLE_SPEED, IDLE_RADIUS_M, IDLE_MIN = 3, 60, timedelta(minutes=3)


def meters(lat1, lng1, lat2, lng2):
    p = math.pi / 180
    h = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lng2 - lng1) * p / 2) ** 2
    return 12742000 * math.asin(math.sqrt(h))


def _still(p):
    return p.get('Velocidad') is not None and p['Velocidad'] <= IDLE_SPEED


def still_runs(points):
    """(first, last) index of every run of still points, each within IDLE_RADIUS_M of its first point."""
    runs, first = [], None
    for n, p in enumerate(points):
        if first is not None and _still(p) and meters(
                zeek_coord(points[first]['Latitud']), zeek_coord(points[first]['Longitud']),
                zeek_coord(p['Latitud']), zeek_coord(p['Longitud'])) <= IDLE_RADIUS_M:
            continue
        if first is not None:
            runs.append((first, n - 1))
        first = n if _still(p) else None
    if first is not None:
        runs.append((first, len(points) - 1))
    return runs


def legs(trips):
    """Every stretch of driving in the day, oldest first:
    {'start', 'end', 'leave', 'start_kind', 'end_kind', 'from_lat', 'from_lng', 'lat', 'lng', 'km', 'place'}.
    start_kind is 'parked' (ignition on) or 'idle' (pulling away from an engine-on stop); end_kind is
    'idle' or 'parked' (the ignition went off there). from_lat/from_lng is where it started, lat/lng where it
    ended, leave when the vehicle moved on from there (None for the day's last stop), place Zeek's geofence
    name, if any."""
    out = []
    for trip in trips:
        points = trip['listaUbicaciones']
        last = len(points) - 1
        runs = still_runs(points)
        end = runs[-1][0] if runs and runs[-1][1] == last else last
        start, start_kind = 0, 'parked'
        for a, b in runs:
            if a > 0 and b < last and zeek_time(points[b]['Fecha']) - zeek_time(points[a]['Fecha']) >= IDLE_MIN:
                out.append(_leg(points, start, a, start_kind, 'idle'))
                start, start_kind = b, 'idle'
        out.append(_leg(points, start, max(end, start), start_kind, 'parked'))
    for leg, nxt in zip(out, out[1:] + [None]):
        leg['leave'] = nxt and nxt['start']
    return out


def _leg(points, a, b, start_kind, end_kind):
    p, q = points[a], points[b]
    return {'start': zeek_time(p['Fecha']), 'end': zeek_time(q['Fecha']), 'start_kind': start_kind, 'end_kind': end_kind,
            'from_lat': zeek_coord(p['Latitud']), 'from_lng': zeek_coord(p['Longitud']),
            'lat': zeek_coord(q['Latitud']), 'lng': zeek_coord(q['Longitud']),
            'km': round((int(q['odo']) - int(p['odo'])) / 1000, 2) if q.get('odo') and p.get('odo') else None,
            'place': points[-1].get('ng') if end_kind == 'parked' else None}


def stops(day_legs):
    """Where each leg ended, until the vehicle moved on: the rows of VehicleStop."""
    return [{'arrive': leg['end'], 'leave': leg['leave'], 'lat': leg['lat'], 'lng': leg['lng'],
             'engine_on': leg['end_kind'] == 'idle'} for leg in day_legs]

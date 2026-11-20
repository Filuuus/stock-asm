"""Route sheets built from the GPS: each salesman's day (ZONA 1, ZONA 2), the service crew's (SERVICIOS) and every
other vehicle's (OTRAS UNIDADES), one monthly workbook in the shared folder (ROUTE_SHEETS_EXPORT_DIR/<year>/).

Every stop is named with the shared matcher (matching.py) and matched to the ERP's invoices around that day:
- A stop at a client place lists the clients there that were invoiced from the day before to two days after (all of
  them when none were), with the sale and folios. Credit sales are invoiced the next day, so the nightly run also
  redoes the day before.
- An unknown stop under MIN_DWELL is a driving pause and is left out; a longer one suggests clients invoiced around
  that day whose town pin is within NEAR_TOWN_M, in the same zone. It goes to PENDIENTES for someone to identify.
- A salesman drives one truck a day: per zone and day, the truck whose stops that zone's salesman invoiced.
- The service crew drives SERVICE_IMEI, or another truck on a day it visited none of its calendar's clients and
  that truck did (the crew's Notion calendar, NOTION_SERVICE_TASKS_DB). Its stops show the calendar activity and
  the service invoice (product 0000 SERVICIO / 0004 SERVICIO DE EMERGENCIA from the SERVICIOS agent, or with no
  part description: 0000 is also a generic code for parts).

Names come live from the ERP (read-only) and the saved places; nothing here is stored. Based on the review workbooks
built by hand in Oct-Nov 2026, which the sales and service staff checked."""

import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.db import connections
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from profitability.models import SavedPlace
from profitability.places import territory

from .matching import CLIENT_M, SPOT_M, StopMatcher
from .models import VehicleDayKm, VehicleStop
from .notion import notion, notion_query, page_title
from .timeline import meters
from .zeek import LOCAL_TZ

ZONES = {1: 'ZONA 1', 2: 'ZONA 2'}
SERVICIOS_AGENT = 5
MIN_DWELL = timedelta(minutes=3)
SAME_VISIT = timedelta(minutes=5)       # back-to-back stops at the same client: one visit split by the GPS
SERVICE_SAME_VISIT = timedelta(minutes=10)
NEAR_TOWN_M = 6000
SERVICE_INVOICE_DAYS = 4                # service invoices are entered up to a few days after the job
BOLD, HEAD_FILL, GRAY = Font(bold=True), PatternFill('solid', fgColor='DDEBF7'), Font(italic=True, color='808080')


def hm(t):
    return t.astimezone(LOCAL_TZ).strftime('%H:%M') if t else ''


def maps(lat, lng):
    return f'https://maps.google.com/?q={lat:.5f},{lng:.5f}'


class Erp:
    """What the sheets need from the ERP for a range of days, read once."""

    def __init__(self, first, last):
        with connections['erp'].cursor() as c:
            c.execute('SELECT CIDCLIENTEPROVEEDOR, CCODIGOCLIENTE, CRAZONSOCIAL FROM admClientes')
            self.clients = {k: (code, name) for k, code, name in c.fetchall()}
            c.execute('SELECT CIDCATALOGO, CCIUDAD, CMUNICIPIO FROM admDomicilios WHERE CTIPOCATALOGO = 1 AND CTIPODIRECCION = 0')
            self.towns = {k: town(ci, mu) for k, ci, mu in c.fetchall()}
            # A client's zone: the agent with the most invoices in the last three years.
            c.execute("""SELECT CIDCLIENTEPROVEEDOR, CIDAGENTE, COUNT(*) FROM admDocumentos
                         WHERE CIDDOCUMENTODE = 4 AND CCANCELADO = 0 AND CFECHA >= %s
                         GROUP BY CIDCLIENTEPROVEEDOR, CIDAGENTE""", [date(first.year - 3, 1, 1)])
            best = {}
            for k, agent, n in c.fetchall():
                if n > best.get(k, (0, 0))[1]:
                    best[k] = (agent, n)
            self.zone_of = {k: a for k, (a, _) in best.items() if a in ZONES}
            c.execute("""SELECT CIDCLIENTEPROVEEDOR, CAST(CFECHA AS date), CTOTAL, CSERIEDOCUMENTO, CFOLIO, CIDAGENTE
                         FROM admDocumentos WHERE CIDDOCUMENTODE = 4 AND CCANCELADO = 0 AND CFECHA BETWEEN %s AND %s""",
                      [first - timedelta(days=14), last + timedelta(days=SERVICE_INVOICE_DAYS)])
            self.invoices = [(k, d, float(t), f'{(s or "").strip()}{int(f)}', a) for k, d, t, s, f, a in c.fetchall()]
            c.execute("""SELECT d.CIDDOCUMENTO, d.CIDCLIENTEPROVEEDOR, CAST(d.CFECHA AS date), d.CTOTAL, d.CSERIEDOCUMENTO,
                                d.CFOLIO, d.CIDAGENTE, p.CCODIGOPRODUCTO,
                                LTRIM(RTRIM(ISNULL(m.CTEXTOEXTRA1, '') + ' ' + ISNULL(CAST(m.COBSERVAMOV AS varchar(400)), '')))
                         FROM admMovimientos m JOIN admDocumentos d ON d.CIDDOCUMENTO = m.CIDDOCUMENTO
                         JOIN admProductos p ON p.CIDPRODUCTO = m.CIDPRODUCTO
                         WHERE d.CIDDOCUMENTODE = 4 AND d.CCANCELADO = 0 AND p.CCODIGOPRODUCTO IN ('0000', '0004')
                           AND d.CFECHA BETWEEN %s AND %s""", [first, last + timedelta(days=SERVICE_INVOICE_DAYS)])
            self.service_invoices = service_invoices(c.fetchall())

    def sold(self, cid, day, before=1, after=2):
        return [x for x in self.invoices if x[0] == cid and day - timedelta(days=before) <= x[1] <= day + timedelta(days=after)]

    def name(self, cid):
        return self.clients.get(cid, ('', str(cid)))[1]


def town(city, municipality):
    """'CERRO GORDO - TEPATITLÁN DE MORELOS', or one name when both say the same (accents aside)."""
    plain = lambda x: unicodedata.normalize('NFD', x).encode('ascii', 'ignore').decode()
    parts = {}
    for x in (city, municipality):
        if x and x.strip():
            parts.setdefault(plain(x.strip().upper()), x.strip().upper())
    return ' - '.join(parts.values())


def service_invoices(lines):
    """Invoices with a service concept, from (doc, client, day, total, serie, folio, agent, product, text) lines."""
    found = {}
    for doc, cid, day, total, serie, folio, agent, code, text in lines:
        if code == '0000' and agent != SERVICIOS_AGENT and text:
            continue  # a part sold under the generic code
        x = found.setdefault(doc, {'cid': cid, 'day': day, 'total': float(total),
                                   'folio': f'{(serie or "").strip()}{int(folio)}', 'concept': []})
        x['concept'].append(text.split('\r')[0][:40] or ('SERVICIO DE EMERGENCIA' if code == '0004' else 'SERVICIO'))
    return sorted(found.values(), key=lambda x: x['day'])


def calendar_tasks(first, last):
    """The crew's Notion calendar entries overlapping the range, with their clients' ERP ids."""
    if not settings.NOTION_SERVICE_TASKS_DB:
        return []
    pages = notion_query(settings.NOTION_SERVICE_TASKS_DB, {'and': [
        {'property': 'Fecha', 'date': {'on_or_after': (first - timedelta(days=31)).isoformat()}},
        {'property': 'Fecha', 'date': {'on_or_before': last.isoformat()}}]})
    erp_ids, tasks = {}, []
    for page in pages:
        props = page['properties']
        when = props['Fecha']['date']
        if not when:
            continue
        start = date.fromisoformat(when['start'][:10])
        end = date.fromisoformat((when['end'] or when['start'])[:10])
        if end < first:
            continue
        cids = []
        for rel in props.get('Nombre del cliente', {}).get('relation', []):
            if rel['id'] not in erp_ids:
                number = notion('GET', f"pages/{rel['id']}")['properties'].get('ID ERP', {}).get('number')
                erp_ids[rel['id']] = int(number) if number else None
            if erp_ids[rel['id']]:
                cids.append(erp_ids[rel['id']])
        tasks.append({'start': start, 'end': end, 'title': page_title(page).strip(), 'cids': cids,
                      'state': (props.get('Estado', {}).get('status') or {}).get('name', '')})
    return tasks


class Month:
    """One run: the stops, places, ERP data and calendar for the days first..last."""

    def __init__(self, first, last, unit_names, erp=None, tasks=None, places=None, stops=None, km=None):
        self.first, self.last, self.unit_names = first, last, unit_names
        self.erp = erp or Erp(first, last)
        self.tasks = calendar_tasks(first, last) if tasks is None else tasks
        places = list(SavedPlace.objects.exclude(lat=None)) if places is None else places
        self.matcher = StopMatcher(places)
        self.towns_of = defaultdict(list)  # client -> town-level pins, for guessing who an unknown stop was
        for p in places:
            for c in (p.client_ids if p.approximate else ()):
                self.towns_of[c].append(p)
        self.places_of = defaultdict(list)
        for p in self.matcher.clients:
            for c in p.client_ids:
                self.places_of[c].append(p)
        self.labeled = [(p.lat, p.lng, self.erp.zone_of[c]) for p in self.matcher.clients for c in p.client_ids[:1]
                        if c in self.erp.zone_of]
        stops = stops if stops is not None else VehicleStop.objects.filter(day__range=(first, last)).order_by('arrive')
        self.by_day = defaultdict(list)
        for s in stops:
            self.by_day[s.day].append(s)
        self.km = km if km is not None else {(k.imei, k.day): float(k.km) for k in
                                             VehicleDayKm.objects.filter(day__range=(first, last))}
        self.service_imei = settings.FLEET_SERVICE_IMEI

    def unit(self, imei):
        return self.unit_names.get(imei, imei[-4:])

    def at_client(self, s, cid):
        return any(meters(s.lat, s.lng, p.lat, p.lng) <= CLIENT_M for p in self.places_of.get(cid, ()))

    def on(self, day):
        return [t for t in self.tasks if t['start'] <= day <= t['end']]

    # --- who drove what -----------------------------------------------------------------------------------------

    def crew_units(self, day):
        """The crew's truck(s): SERVICE_IMEI, or the trucks that stopped at a calendar client's place when it didn't."""
        clients = [c for t in self.on(day) for c in t['cids']]
        own = [s for s in self.by_day[day] if s.imei == self.service_imei]
        if any(self.at_client(s, c) for s in own for c in clients):
            return {self.service_imei}
        return {self.service_imei} | {s.imei for s in self.by_day[day] for c in clients if self.at_client(s, c)}

    # --- rows ---------------------------------------------------------------------------------------------------

    def visit_rows(self, day, imei):
        """The day's stops of one truck as sheet rows (company sites left out: they give the day's start and end)."""
        rows = []
        for s in self.by_day[day]:
            if s.imei != imei:
                continue
            found = self.matcher.match(s.lat, s.lng)
            if found and found['kind'] == 'base':
                continue
            short = not s.leave or s.leave - s.arrive < MIN_DWELL
            client = found and found['kind'] == 'client'
            if not client and not found and short:
                continue  # a driving pause
            row = {'s': s, 'arrive': s.arrive, 'leave': s.leave, 'found': found, 'cids': [], 'sale': None, 'folios': '',
                   'agents': set(), 'zone': ZONES[territory(s.lat, s.lng, self.labeled)], 'obs': ''}
            if client:
                place = found['place']
                sold = {c: self.erp.sold(c, day) for c in place.client_ids}
                cids = [c for c in place.client_ids if sold[c]] or place.client_ids
                row.update(cids=cids, sale=round(sum(x[2] for c in cids for x in sold[c]), 2) or None,
                           folios=', '.join(x[3] for c in cids for x in sold[c]), agents={x[4] for c in cids for x in sold[c]},
                           obs=f"Lugar conocido a {found['meters']} m" + (' (parada corta)' if short else '')
                           + (f'; mismo lugar: {len(place.client_ids)} clientes' if len(place.client_ids) > 1 and len(cids) == 1 else ''))
            elif found:
                row['obs'] = f"Lugar conocido a {found['meters']} m"
            else:
                row['obs'] = self.unknown(s, day, row['zone'])
            if s.engine_on:
                row['obs'] += '; con motor encendido'
            prev = rows[-1] if rows else None
            if prev and row['cids'] and prev['cids'] == row['cids'] and prev['leave'] and s.arrive - prev['leave'] <= SAME_VISIT:
                prev['leave'] = s.leave
                continue
            if row['folios'] and any(r['folios'] == row['folios'] for r in rows):
                # the same client again that day (delivering at one stop, collecting at another): the sale once
                row.update(sale=None, folios='', obs=row['obs'] + '; venta en la parada anterior')
            rows.append(row)
        return rows

    def unknown(self, s, day, zone):
        near = min((meters(s.lat, s.lng, p.lat, p.lng) for p in self.matcher.clients), default=0)
        invoiced = {x[0] for x in self.erp.invoices if day - timedelta(days=14) <= x[1] <= day + timedelta(days=2)}
        cands = sorted((min(d), c) for c in invoiced if not self.places_of.get(c) and ZONES.get(self.erp.zone_of.get(c)) == zone
                       for d in [[meters(s.lat, s.lng, p.lat, p.lng) for p in self.towns_of.get(c, ())]] if d and min(d) <= NEAR_TOWN_M)
        return f'Sin cliente (lugar conocido más cercano a {near / 1000:.1f} km)' + (
            '; posibles: ' + '; '.join(f'{self.erp.name(c)} ({self.erp.clients[c][0]}, su población a {d / 1000:.1f} km)'
                                       for d, c in cands[:3]) if cands else '')

    def day_bounds(self, day, imei, rows):
        """When the truck left a company site before its first visit, and got back to one after the last."""
        bases = [s for s in self.by_day[day] if s.imei == imei and (f := self.matcher.match(s.lat, s.lng)) and f['kind'] == 'base']
        first, last = rows[0]['arrive'], rows[-1]['leave'] or rows[-1]['arrive']
        out = max((b.leave for b in bases if b.leave and b.leave <= first), default=None)
        back = min((b.arrive for b in bases if b.arrive >= last), default=None)
        return out, back

    def what(self, row):
        f = row['found']
        if row['cids']:
            return ' / '.join(dict.fromkeys(self.erp.name(c) for c in row['cids']))  # one name for two accounts
        if f and f['kind'] != 'client':
            return f['place'].name or '¿? (revisado, sin nombre)'
        return '¿?'

    # --- the sales routes ---------------------------------------------------------------------------------------

    def routes(self):
        """{(day, imei): rows} for every truck but the crew's, and {(zone, day): imei} for each salesman's truck."""
        forms, route = {}, {}
        for day in sorted(self.by_day):
            crew = self.crew_units(day)
            for imei in sorted({s.imei for s in self.by_day[day]} - crew):
                rows = self.visit_rows(day, imei)
                if rows:
                    forms[day, imei] = rows
        for (day, imei), rows in forms.items():
            zone = Counter(r['zone'] for r in rows).most_common(1)[0][0]
            agent = next(a for a, z in ZONES.items() if z == zone)
            score = (sum(agent in r['agents'] for r in rows), sum(bool(r['cids']) and r['zone'] == zone for r in rows))
            if any(score) and score > route.get((zone, day), (None, (0, 0)))[1]:
                route[zone, day] = (imei, score)
        return forms, {k: v[0] for k, v in route.items()}


# --- workbook -------------------------------------------------------------------------------------------------------

ZONE_COLS = ['No.', 'CLAVE', 'NOMBRE CLIENTE', 'POBLACION', 'LLEGADA', 'SALIDA', 'VENTA (ERP)', 'FACTURA',
             'OBSERVACIONES', 'MAPA']
ZONE_WIDTHS = [5, 13, 42, 30, 8, 8, 13, 18, 70, 10]
SERVICE_COLS = ['No.', 'UNIDAD', 'NOMBRE DEL CONTACTO', 'RANCHO', 'LLEGADA', 'SALIDA', 'MIN', 'ACTIVIDAD (CALENDARIO)',
                'FACTURA', 'MONTO', 'CONCEPTO', 'OBSERVACIONES', 'MAPA']
SERVICE_WIDTHS = [5, 14, 40, 22, 8, 8, 6, 34, 10, 12, 30, 42, 10]


def _header(ws, cols):
    ws.append(cols)
    for c in ws[ws.max_row]:
        c.font, c.fill = BOLD, HEAD_FILL


def build_workbook(month):
    wb = Workbook()
    pending_ws = wb.active
    pending_ws.title = 'PENDIENTES'
    sheets = {}
    for title, widths in [*((z, ZONE_WIDTHS) for z in ZONES.values()), ('SERVICIOS', SERVICE_WIDTHS),
                          ('OTRAS UNIDADES', ZONE_WIDTHS)]:
        sheets[title] = wb.create_sheet(title)
        for i, w in enumerate(widths):
            sheets[title].column_dimensions[chr(65 + i)].width = w
    pending = []
    forms, route = month.routes()
    salesman = {(day, imei): zone for (zone, day), imei in route.items()}
    for (day, imei), rows in sorted(forms.items()):
        zone = salesman.get((day, imei))
        ws = sheets[zone or 'OTRAS UNIDADES']
        _zone_block(ws, month, day, imei, rows, zone or Counter(r['zone'] for r in rows).most_common(1)[0][0], pending)
    for day in sorted(month.by_day):
        _service_block(sheets['SERVICIOS'], month, day, pending)
    _pending_sheet(pending_ws, pending)
    return wb


def _zone_block(ws, month, day, imei, rows, zone, pending):
    out, back = month.day_bounds(day, imei, rows)
    ws.append([zone, None, 'UNIDAD:', month.unit(imei), 'FECHA:', f'{day:%d/%m/%Y}'])
    ws.append([None, None, 'HORA SALIDA:', hm(out), 'HORA LLEGADA:', hm(back), 'KM (GPS):', month.km.get((imei, day))])
    for c in ws[ws.max_row - 1] + ws[ws.max_row]:
        c.font = BOLD
    _header(ws, ZONE_COLS)
    for n, r in enumerate(rows, 1):
        s = r['s']
        codes = [month.erp.clients.get(c, ('', ''))[0] for c in r['cids']]
        obs = r['obs'] + ('' if r['zone'] == zone or ws.title == 'OTRAS UNIDADES' else f"; territorio {r['zone']}")
        ws.append([n, ' / '.join(codes), month.what(r), ' / '.join(dict.fromkeys(month.erp.towns.get(c, '') for c in r['cids'])),
                   hm(r['arrive']), hm(r['leave']), r['sale'], r['folios'], obs, 'Ver mapa'])
        ws.cell(ws.max_row, 10).hyperlink = maps(s.lat, s.lng)
        ws.cell(ws.max_row, 7).number_format = '$#,##0.00'
        ws.cell(ws.max_row, 9).alignment = Alignment(wrap_text=True, vertical='top')
        if not r['found']:
            pending.append(_pending_row(ws.title, month, day, rows, n, obs))
    ws.append([])


def _service_block(ws, month, day, pending):
    units = month.crew_units(day)
    rows = []
    for s in sorted((s for s in month.by_day[day] if s.imei in units), key=lambda s: s.arrive):
        found = month.matcher.match(s.lat, s.lng)
        if not found and (not s.leave or s.leave - s.arrive < MIN_DWELL):
            continue
        key = found and found['place'].pk
        prev = next((r for r in reversed(rows) if r['s'].imei == s.imei), None)
        if prev and key and prev['key'] == key and prev['leave'] and s.arrive - prev['leave'] <= SERVICE_SAME_VISIT:
            prev['leave'], prev['engine_on'] = s.leave, prev['engine_on'] or s.engine_on
            continue
        rows.append({'key': key, 'found': found, 's': s, 'arrive': s.arrive, 'leave': s.leave, 'engine_on': s.engine_on,
                     'cids': found['place'].client_ids if found and found['kind'] == 'client' else []})
    if not any(r['found'] and r['found']['kind'] != 'base' or not r['found'] for r in rows):
        return  # stayed at the office or warehouse
    base = lambda r: r['found'] and r['found']['kind'] == 'base'
    out = rows[0]['leave'] if base(rows[0]) else rows[0]['arrive']
    back = rows[-1]['arrive'] if base(rows[-1]) else rows[-1]['leave'] or rows[-1]['arrive']
    ws.append(['SERVICIOS', None, 'UNIDAD:', ', '.join(month.unit(u) for u in sorted(units)), 'FECHA:', f'{day:%d/%m/%Y}'])
    ws.append([None, None, 'SALIDA:', hm(out), 'LLEGADA:', hm(back), 'KM (GPS):',
               round(sum(month.km.get((u, day), 0) for u in units), 2)])
    for c in ws[ws.max_row - 1] + ws[ws.max_row]:
        c.font = BOLD
    _header(ws, SERVICE_COLS)
    today = month.on(day)
    invoiced = lambda r: [x for x in month.erp.service_invoices if x['cid'] in r['cids']
                          and day <= x['day'] <= day + timedelta(days=SERVICE_INVOICE_DAYS)]
    done = {id(t) for r in rows for t in today if set(t['cids']) & set(r['cids'])}
    any_invoice = lambda r: [x for c in r['cids'] for x in month.erp.sold(c, day, 1, SERVICE_INVOICE_DAYS)]
    guesses = calendar_guesses([t for t in today if id(t) not in done], rows, today, any_invoice)
    for n, r in enumerate(rows, 1):
        s, f = r['s'], r['found']
        task = [t for t in today if set(t['cids']) & set(r['cids'])]
        inv = invoiced(r)
        obs = (f"{'Cliente' if r['cids'] else 'Lugar'} a {f['meters']} m" if f else
               f"Sin cliente (lugar conocido más cercano a "
               f"{min((meters(s.lat, s.lng, p.lat, p.lng) for p in month.matcher.clients), default=0) / 1000:.1f} km)")
        if r['engine_on']:
            obs += '; con motor encendido'
        guess = guesses.get(id(r))
        if guess:
            done.add(id(guess))
            obs += f"; según el calendario sería {' / '.join(month.erp.name(c) for c in guess['cids'])} (sin confirmar)"
        ws.append([n, month.unit(s.imei), month.what(r), ' / '.join(dict.fromkeys(month.erp.towns[c] for c in r['cids']
                                                                                if month.erp.towns.get(c))),
                   hm(r['arrive']), hm(r['leave']), round((r['leave'] - r['arrive']).total_seconds() / 60) if r['leave'] else None,
                   '; '.join(t['title'] for t in task) or (guess and f"¿{guess['title']}?") or None,
                   ', '.join(x['folio'] for x in inv) or None,
                   round(sum(x['total'] for x in inv), 2) or None,
                   '; '.join(dict.fromkeys(c for x in inv for c in x['concept'])) or None, obs, 'Ver mapa'])
        ws.cell(ws.max_row, 13).hyperlink = maps(s.lat, s.lng)
        ws.cell(ws.max_row, 10).number_format = '$#,##0.00'
        if not f:
            pending.append(_pending_row('SERVICIOS', month, day, rows, n, obs))
    for t in today:
        if id(t) not in done and day in (t['start'], t['end']):
            others = [x for x in month.by_day[day] if x.imei not in units and any(month.at_client(x, c) for c in t['cids'])]
            if others:  # the crew split up, or someone else took care of it
                why = 'pasó otra unidad: ' + ', '.join(f'{month.unit(x.imei)} {hm(x.arrive)}' for x in others)
            elif any(month.places_of.get(c) for c in t['cids']):
                why = 'ninguna unidad paró en su lugar ese día'
            else:
                why = 'cliente sin lugar guardado'
            ws.append([None, None, ' / '.join(month.erp.name(c) for c in t['cids']), None, None, None, None, t['title'],
                       None, None, None, f"En el calendario, {why} ({t['state']})"])
            for c in ws[ws.max_row]:
                c.font = GRAY
    ws.append([])


def calendar_guesses(missed, rows, today, invoiced, min_minutes=10):
    """{id(row): task} for calendar jobs with no stop at their client: each takes the longest crew stop of the day
    nothing else explains (10+ minutes), an unknown or unnamed spot first, else a client's place where that client
    had no job and no invoice of any kind around that day (a shared farm). A guess for someone to confirm, never saved on its own."""
    def free(r):
        f, long_enough = r['found'], r['leave'] and (r['leave'] - r['arrive']).total_seconds() >= min_minutes * 60
        if not long_enough or (f and f['kind'] == 'base') or (f and f['kind'] == 'spot' and f['place'].name):
            return None
        if f and f['kind'] == 'client':
            if any(set(t['cids']) & set(r['cids']) for t in today) or invoiced(r):
                return None
            return 1
        return 0
    open_rows = sorted((key, -(r['leave'] - r['arrive']).total_seconds(), n) for n, r in enumerate(rows)
                       if (key := free(r)) is not None)
    guesses = {}
    for t, (_, _, n) in zip(sorted(missed, key=lambda t: t['title']), open_rows):
        guesses[id(rows[n])] = t
    return guesses


def _pending_row(sheet, month, day, rows, n, obs):
    r = rows[n - 1]
    near = lambda x: f"{hm(x['arrive'])} {month.what(x)}"
    return [sheet, day, month.unit(r['s'].imei), hm(r['arrive']), hm(r['leave']),
            round((r['leave'] - r['arrive']).total_seconds() / 60) if r['leave'] else None,
            near(rows[n - 2]) if n > 1 else '(salida)', near(rows[n]) if n < len(rows) else '(regreso)', obs,
            maps(r['s'].lat, r['s'].lng)]


ANSWER = '¿QUÉ ES?'
PERSONAL = ('casa ', 'ludoteca')  # a home: the Notion log shows only "Parada personal"


def _pending_sheet(ws, pending):
    ws.append(['Paradas sin cliente ni nombre todavía. Escribe en ¿QUÉ ES? qué es (un nombre, o la clave o el nombre '
               'del cliente en el sistema) y guarda: esa noche se aprende el lugar y la parada sale con su nombre.'])
    _header(ws, ['#', 'HOJA', 'FECHA', 'UNIDAD', 'LLEGADA', 'SALIDA', 'MIN', 'PARADA ANTERIOR', 'PARADA SIGUIENTE',
                 'OBSERVACIONES', 'MAPA', ANSWER])
    for i, (sheet, day, unit, arrive, leave, dwell, before, after, obs, link) in enumerate(
            sorted(pending, key=lambda x: (x[1], x[3])), 1):
        ws.append([i, sheet, f'{day:%d/%m/%Y}', unit, arrive, leave, dwell, before, after, obs, 'Ver mapa', None])
        ws.cell(ws.max_row, 11).hyperlink = link
    for i, w in enumerate([5, 16, 11, 18, 8, 8, 6, 40, 40, 60, 10, 34]):
        ws.column_dimensions[chr(65 + i)].width = w
    ws.freeze_panes = 'A3'


# --- answers typed into PENDIENTES ---------------------------------------------------------------------------------

def read_answers(path):
    """(lat, lng, text) for every ¿QUÉ ES? typed in a route-sheet workbook's PENDIENTES, located by its map link."""
    try:
        ws = load_workbook(path)['PENDIENTES']
    except (OSError, KeyError, ValueError):  # missing, not a workbook, or no PENDIENTES sheet
        return []
    cols = {c.value: c.column for c in ws[2]}
    if ANSWER not in cols or 'MAPA' not in cols:
        return []
    found = []
    for row in ws.iter_rows(min_row=3):
        text, link = row[cols[ANSWER] - 1].value, row[cols['MAPA'] - 1].hyperlink
        if text is not None and str(text).strip() and link and 'q=' in (link.target or ''):
            lat, lng = map(float, link.target.split('q=')[1].split(','))
            found.append((lat, lng, str(text).strip()))
    return found


def _plain(text):
    return ' '.join(unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode().upper().split())


def save_answers(answers, clients):
    """Learns each typed answer as a place at that stop. An ERP client, by code or by its exact name (accents and
    case aside, only when one client has it), becomes a place of that client; anything else names the spot,
    renaming one already saved within SPOT_M ("Casa ..." marked personal). Returns how many were saved."""
    by_code = {code.strip().upper(): k for k, (code, _) in clients.items() if code}
    by_name = defaultdict(list)
    for k, (_, name) in clients.items():
        if name:
            by_name[_plain(name)].append(k)
    spots = list(SavedPlace.objects.filter(kind='spot').exclude(lat=None))
    saved = 0
    for lat, lng, text in answers:
        cid = by_code.get(text.upper()) or (by_name[_plain(text)][0] if len(by_name.get(_plain(text), [])) == 1 else None)
        if cid:
            if SavedPlace.objects.filter(url=f'hoja:{lat:.5f},{lng:.5f}', client_ids=[cid]).exists():
                continue  # learned on an earlier night (the file still had the answer)
            SavedPlace.objects.update_or_create(url=f'hoja:{lat:.5f},{lng:.5f}', defaults=dict(
                name=clients[cid][1], list_name='Hojas de ruta', lat=lat, lng=lng, client_ids=[cid], matched_by='manual',
                kind=''))
            saved += 1
            continue
        personal = text.lower().startswith(PERSONAL)
        near = min(((meters(lat, lng, p.lat, p.lng), p) for p in spots), key=lambda x: x[0], default=None)
        if near and near[0] <= SPOT_M:
            if (near[1].name, near[1].personal) != (text, personal):
                near[1].name, near[1].personal = text, personal
                near[1].save()
                saved += 1
        else:
            spots.append(SavedPlace.objects.create(url=f'gps:{lat:.5f},{lng:.5f}', name=text, list_name='Hojas de ruta',
                                                   lat=lat, lng=lng, client_ids=[], matched_by='manual', kind='spot',
                                                   personal=personal))
            saved += 1
    return saved


def export_month(year, month_number, unit_names, output_dir=None, today=None):
    """Learns what was typed into the month's PENDIENTES, then rewrites the month's route sheets, up to yesterday,
    in <ROUTE_SHEETS_EXPORT_DIR>/<year>/. Returns (path, answers learned)."""
    from corte_de_caja.exports import save_report
    today = today or datetime.now(LOCAL_TZ).date()
    first = date(year, month_number, 1)
    last = min((first + timedelta(days=32)).replace(day=1) - timedelta(days=1), today - timedelta(days=1))
    output_dir = Path(output_dir or settings.ROUTE_SHEETS_EXPORT_DIR) / str(year)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f'Hojas de ruta {year}-{month_number:02d}.xlsx'
    erp = Erp(first, last)
    learned = save_answers(read_answers(output_dir / filename), erp.clients)
    wb = build_workbook(Month(first, last, unit_names, erp=erp))
    return save_report(wb, output_dir, filename, protect=False), learned

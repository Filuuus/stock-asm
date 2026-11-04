"""Service plan: when each parlor part falls due, which visits to propose, and what to order from GEA.

GEA takes orders only in the first week of each month and they arrive about a month later, so the order
placed in month M has to cover what falls due until the next order lands (end of M+1), plus a buffer of
counter sales (parts sold to clients without a registered parlor), minus general-warehouse stock and what's
already on order. Visits are proposed two months ahead (M+2) so their parts can be ordered in time.

A part's last change = the latest of its invoices to that client (a purchase of at least half the parlor's
quantity) and the changes staff confirmed. Every part gets two intervals, and the order is proposed under both
(the owner compares them before settling on one, 2026-11-04):
- 'gea': GEA's replacement rule, its hours converted with the parlor's daily milking hours; without one,
  the client's own rhythm, then the median across clients.
- 'actual': the client's own rhythm, then the median across clients, then GEA.
Visits are proposed on VISIT_POLICY's dates: the date the crew offers the client.
"""

import math
import re
import statistics
from collections import defaultdict
from datetime import date, timedelta

from django.core.cache import cache
from django.db import connections

from api.services import FACTURA_DOC_TYPE, GENERAL_WAREHOUSE_ID, _gea_products

POLICIES = ('gea', 'actual')
VISIT_POLICY = 'gea'
MONTH_DAYS = 30.44
MERGE_DAYS = 45            # purchases this close together are one change
MAX_GAP_MONTHS = 36        # a longer gap = bought elsewhere, not a replacement cycle
MIN_CLIENTS = 3            # fewer clients than this is no basis for a cross-client interval
STALE_MONTHS = 24          # overdue longer than this: assume bought elsewhere; left out of visits and orders
BUFFER_MONTHS = 2          # counter-sales stock on hand, about the order cycle plus transit
HISTORY_DAYS = 8 * 365
ORDER_DEADLINE_DAY = 7     # GEA takes orders in the first week of the month
CACHE_SECONDS = 600
VISIT_RADIUS_M = 300       # a GPS stop this close to the parlor's saved place counts as being there


def base_code(code):
    """GEA parts are sold under letter-suffixed codes too (7021-2764-010W): one part."""
    return re.sub(r'(?<=\d)[A-Z]$', '', code.strip().upper())


def month_start(d):
    return date(d.year, d.month, 1)


def add_months(d, n):
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def months_between(a, b):
    return (b - a).days / MONTH_DAYS


def merge_purchases(lines):
    """[(client, code, day, qty)] -> {(client, code): [[day, qty], ...]}, purchases within MERGE_DAYS merged."""
    by_key = defaultdict(list)
    for client, code, day, qty in sorted(lines, key=lambda r: r[2]):
        if qty <= 0:
            continue
        events = by_key[(client, code)]
        if events and (day - events[-1][2]).days <= MERGE_DAYS:
            events[-1][1] += qty
            events[-1][2] = day
        else:
            events.append([day, qty, day])  # start, qty, last day in the window
    return {k: [[d, q] for d, q, _ in ev] for k, ev in by_key.items()}


def full_changes(events, minimum):
    """Purchases big enough to be a change (not a top-up)."""
    return [e for e in events if e[1] >= minimum]


def median_gap(events):
    gaps = [g for g in (months_between(a[0], b[0]) for a, b in zip(events, events[1:])) if g <= MAX_GAP_MONTHS]
    return statistics.median(gaps) if gaps else None


def cross_client_months(purchases):
    """{code: months}: median over clients of each client's median gap, when MIN_CLIENTS clients have one."""
    per_code = defaultdict(list)
    for (_, code), events in purchases.items():
        gap = median_gap(full_changes(events, max(q for _, q in events) / 2))
        if gap is not None:
            per_code[code].append(gap)
    return {code: statistics.median(gaps) for code, gaps in per_code.items() if len(gaps) >= MIN_CLIENTS}


def gea_rule(service):
    """(hours, months) of GEA's own replacement rule for the part, shortest first; None without one."""
    rules = [r for r in (service or {}).get('rules', []) if 'reempl' in r['action'].lower() and r['months']]
    if not rules:
        return None
    r = min(rules, key=lambda r: r['months'])
    return r['hours'], r['months']


def gea_months(rule, hours_per_day):
    hours, months = rule
    if hours and hours_per_day:
        return min(months, hours / (hours_per_day * MONTH_DAYS))
    return months


def interval(rule, hours_per_day, own, cross, policy):
    """(months, basis) for one parlor part."""
    gea = (gea_months(rule, hours_per_day), 'GEA') if rule else None
    actual = [x for x in ((own, 'cliente'), (cross, 'clientes')) if x[0]]
    order = [gea] + actual if policy == 'gea' else actual + [gea]
    return next((x for x in order if x), (None, None))


def due_rows(parlors, purchases, confirmed, rules, cross, today, policy):
    """One row per parlor part with its last change, interval and due date.

    parlors: [{'id', 'client', 'hours_per_day', 'parts': [(code, qty)]}]; purchases: merge_purchases();
    confirmed: {(parlor id, code): last confirmed day}; rules: {code: (hours, months)}; cross: {code: months}.
    """
    rows = []
    for p in parlors:
        for code, qty in p['parts']:
            changes = full_changes(purchases.get((p['client'], code), []), qty / 2)
            invoiced = changes[-1][0] if changes else None
            last = max((d for d in (invoiced, confirmed.get((p['id'], code))) if d), default=None)
            months, basis = interval(rules.get(code), p['hours_per_day'], median_gap(changes), cross.get(code), policy)
            due = last + timedelta(days=months * MONTH_DAYS) if last and months else None
            if due is None:
                status = 'unknown'
            elif months_between(due, today) > STALE_MONTHS:
                status = 'stale'
            elif due < today:
                status = 'overdue'
            else:
                status = 'ok'
            rows.append({'parlor': p['id'], 'client': p['client'], 'code': code, 'quantity': qty,
                         'last_change': last, 'last_invoice': invoiced,
                         'months': round(months, 1) if months else None, 'basis': basis,
                         'due': due, 'status': status})
    return rows


def plannable(row):
    return row['due'] is not None and row['status'] != 'stale'


def propose_visits(rows, month, open_parts):
    """{parlor id: [(code, qty)]}: parts due by the end of `month` (overdue ones too) that no open visit
    already carries. open_parts: {(parlor id, code)} in proposed or scheduled visits."""
    end = add_months(month, 1)
    visits = defaultdict(list)
    for r in rows:
        if plannable(r) and r['due'] < end and (r['parlor'], r['code']) not in open_parts:
            visits[r['parlor']].append((r['code'], r['quantity']))
    return dict(visits)


def counter_monthly(lines, registered_clients, today):
    """{code: units a month} sold over the last 12 months to clients without a registered parlor."""
    since = today - timedelta(days=365)
    units = defaultdict(float)
    for client, code, day, qty in lines:
        if day >= since and client not in registered_clients:
            units[code] += qty
    return {code: u / 12 for code, u in units.items()}


def order_proposal(rows, order_month, stock, on_order, counter):
    """What to order from GEA in `order_month`: parts falling due until the next order arrives (end of the
    following month), plus BUFFER_MONTHS of counter sales, minus stock and open orders."""
    cover_until = add_months(order_month, 2)
    service = defaultdict(int)
    for r in rows:
        if plannable(r) and r['due'] < cover_until:
            service[r['code']] += r['quantity']
    lines = []
    for code in sorted(set(service) | {c for c, u in counter.items() if u > 0}):
        buffer = math.ceil(counter.get(code, 0) * BUFFER_MONTHS)
        have = max(stock.get(code, 0), 0) + on_order.get(code, 0)
        need = service[code] + buffer - have
        if need > 0:
            lines.append({'code': code, 'services': service[code], 'buffer': buffer,
                          'stock': stock.get(code, 0), 'on_order': on_order.get(code, 0), 'order': math.ceil(need)})
    return lines


def shortages(visits, stock, today, days=30):
    """Parts that open visits in the next `days` need beyond general-warehouse stock: {code: missing}."""
    until = today + timedelta(days=days)
    need = defaultdict(int)
    for v in visits:
        when = v['date'] or v['month']
        if v['status'] in ('proposed', 'scheduled') and when <= until:
            for part in v['parts']:
                need[part['code']] += part['quantity']
    return {code: n - max(stock.get(code, 0), 0) for code, n in need.items() if n > max(stock.get(code, 0), 0)}


def meters(a, b):
    """Distance between two (lat, lng) points."""
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def was_there(stops, places):
    """Days a GPS stop was within VISIT_RADIUS_M of any of the places: [(day, (lat, lng))] -> sorted days."""
    return sorted({day for day, point in stops if any(meters(point, p) <= VISIT_RADIUS_M for p in places)})


# ---------- ERP reads (read-only), cached like the other ERP-backed pages

def fetch_invoice_lines(codes, since):
    """[(client code, base product code, day, units)] of invoices since `since` for parts with these codes."""
    codes = sorted(codes)
    if not codes:
        return []
    key = f'maintenance_lines_v1_{since}_{hash(tuple(codes))}'
    rows = cache.get(key)
    if rows is None:
        likes = ' OR '.join(['p.CCODIGOPRODUCTO LIKE %s'] * len(codes))
        with connections['erp'].cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.CCODIGOCLIENTE, p.CCODIGOPRODUCTO, d.CFECHA, m.CUNIDADES
                FROM admMovimientos m
                JOIN admDocumentos d ON d.CIDDOCUMENTO = m.CIDDOCUMENTO
                JOIN admProductos p ON p.CIDPRODUCTO = m.CIDPRODUCTO
                JOIN admClientes c ON c.CIDCLIENTEPROVEEDOR = d.CIDCLIENTEPROVEEDOR
                WHERE d.CIDDOCUMENTODE = %s AND d.CCANCELADO = 0 AND d.CFECHA >= %s AND ({likes})
                """,
                [FACTURA_DOC_TYPE, since, *[f'{c}%' for c in codes]],
            )
            wanted = set(codes)
            rows = [(client.strip(), base_code(code), day.date(), float(qty))
                    for client, code, day, qty in cursor.fetchall() if base_code(code) in wanted]
        cache.set(key, rows, CACHE_SECONDS)
    return rows


def fetch_products(codes):
    """({base code: units in the general warehouse}, {base code: name}); letter-suffixed codes of one part
    add up."""
    if not codes:
        return {}, {}
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            """
            SELECT p.CCODIGOPRODUCTO, p.CNOMBREPRODUCTO, e.CENTRADASPERIODO12 - e.CSALIDASPERIODO12
            FROM admProductos p
            LEFT JOIN admExistenciaCosto e ON e.CIDPRODUCTO = p.CIDPRODUCTO AND e.CIDALMACEN = %s
              AND e.CIDEJERCICIO = (SELECT MAX(CIDEJERCICIO) FROM admExistenciaCosto WHERE CIDALMACEN = %s)
            """,
            [GENERAL_WAREHOUSE_ID, GENERAL_WAREHOUSE_ID],
        )
        stock, names = defaultdict(float), {}
        for code, name, units in cursor.fetchall():
            base = base_code(code)
            if base in codes:
                stock[base] += float(units or 0)
                if base == code.strip().upper() or base not in names:
                    names[base] = name.strip()
    return {c: round(u, 2) for c, u in stock.items()}, names


def fetch_clients(codes):
    """{client code: (ERP id, name)}, resolved live."""
    if not codes:
        return {}
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            f"SELECT CCODIGOCLIENTE, CIDCLIENTEPROVEEDOR, CRAZONSOCIAL FROM admClientes "
            f"WHERE CCODIGOCLIENTE IN ({', '.join(['%s'] * len(codes))})",
            list(codes),
        )
        return {code.strip(): (cid, name.strip()) for code, cid, name in cursor.fetchall()}


def gea_rules(codes):
    by_base = {base_code(k): v for k, v in _gea_products().items()}
    return {c: r for c in codes if (r := gea_rule(by_base.get(c, {}).get('service')))}


# ---------- the plan, from the local registry plus live ERP data

def build_plan(today):
    from fleet.models import VehicleStop
    from profitability.models import SavedPlace

    from .models import OrderLine, Parlor, PartChange, Visit

    parlors = [{'id': p.id, 'client': p.client_code, 'label': p.label, 'hours_per_day': p.milking_hours_per_day,
                'parts': [(x.code, x.quantity) for x in p.parts.all()]}
               for p in Parlor.objects.filter(active=True).prefetch_related('parts')]
    codes = {code for p in parlors for code, _ in p['parts']}
    lines = fetch_invoice_lines(codes, today - timedelta(days=HISTORY_DAYS))
    purchases = merge_purchases(lines)
    confirmed = {}
    for c in PartChange.objects.filter(parlor__active=True):
        key = (c.parlor_id, c.code)
        confirmed[key] = max(confirmed.get(key, c.date), c.date)
    rules, cross = gea_rules(codes), cross_client_months(purchases)
    rows_by = {policy: due_rows(parlors, purchases, confirmed, rules, cross, today, policy) for policy in POLICIES}
    rows = rows_by[VISIT_POLICY]

    stock, names = fetch_products(codes)
    on_order = defaultdict(int)
    for o in OrderLine.objects.filter(received_on__isnull=True):
        on_order[o.code] += o.quantity
    counter = counter_monthly(lines, {p['client'] for p in parlors}, today)
    this_month = month_start(today)
    orders = {policy: order_proposal(r, this_month, stock, on_order, counter) for policy, r in rows_by.items()}

    visits = list(Visit.objects.filter(parlor__active=True).exclude(status='cancelled').order_by('month'))
    open_parts = {(v.parlor_id, part['code']) for v in visits if v.status in ('proposed', 'scheduled')
                  for part in v.parts}
    visit_month = add_months(this_month, 2)
    proposals = propose_visits(rows, visit_month, open_parts)

    clients = fetch_clients({p['client'] for p in parlors})
    places = defaultdict(list)
    for place in SavedPlace.objects.filter(approximate=False, lat__isnull=False):
        for cid in place.client_ids:
            places[cid].append((place.lat, place.lng))
    visit_dicts = []
    for v in visits:
        client = next(p['client'] for p in parlors if p['id'] == v.parlor_id)
        cid = clients.get(client, (None, ''))[0]
        gps = None
        if v.date and places.get(cid):
            stops = VehicleStop.objects.filter(day__range=(v.date - timedelta(days=3), v.date + timedelta(days=3)))
            gps = [d.isoformat() for d in was_there([(s.day, (s.lat, s.lng)) for s in stops], places[cid])]
        visit_dicts.append({'id': v.id, 'parlor': v.parlor_id, 'month': v.month, 'date': v.date,
                            'status': v.status, 'parts': v.parts, 'gps_days': gps,
                            'has_place': bool(places.get(cid))})

    missing = shortages(visit_dicts, stock, today)
    alerts = []
    ordered_this_month = OrderLine.objects.filter(month=this_month).exists()
    if today.day <= ORDER_DEADLINE_DAY and not ordered_this_month and any(orders.values()):
        alerts.append({'kind': 'order_window', 'deadline': today.replace(day=ORDER_DEADLINE_DAY)})
    if missing:
        alerts.append({'kind': 'missing_parts', 'parts': missing})
    late = [v['id'] for v in visit_dicts if v['status'] == 'scheduled' and v['date'] and v['date'] < today]
    if late:
        alerts.append({'kind': 'unconfirmed_visits', 'visits': late})
    if proposals:
        alerts.append({'kind': 'visits_to_schedule', 'month': visit_month, 'parlors': len(proposals)})

    by_parlor = defaultdict(list)
    for r, other in zip(rows, rows_by['actual' if VISIT_POLICY == 'gea' else 'gea']):  # same parts, same order
        by_parlor[r['parlor']].append({**r, 'alternative': {k: other[k] for k in ('months', 'basis', 'due', 'status')}})
    return {
        'visit_policy': VISIT_POLICY,
        'names': names,
        'stock': stock,
        'parlors': [{**{k: p[k] for k in ('id', 'client', 'label', 'hours_per_day')},
                     'name': clients.get(p['client'], (None, ''))[1],
                     'parts': sorted(by_parlor[p['id']], key=lambda r: (r['due'] is None, r['due'] or today))}
                    for p in parlors],
        'visits': visit_dicts,
        'proposed_visits': {'month': visit_month,
                            'parlors': [{'parlor': pid, 'parts': [{'code': c, 'quantity': q} for c, q in parts]}
                                        for pid, parts in proposals.items()]},
        'orders': {'month': this_month, **orders},
        'alerts': alerts,
    }

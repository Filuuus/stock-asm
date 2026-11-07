"""Service plan: when each client's parlor parts fall due, and what to order from GEA.

A part's last change is its latest invoice to that client for at least half the parlor's quantity: an invoice
for the parts is the record that the service was done (no confirmations in this site; scheduling lives in the
crew's Notion calendar). Its interval follows GEA (the owner's choice, 2026-11-04): GEA's replacement rule, its hours
converted with the parlor's daily milking hours; without one, the client's own rhythm, then the median across
clients, then the calendar's own RECAMBIO.

GEA takes the order on the first Wednesday of the month (from memory, to confirm) and it arrives about a month
later, so an order has to cover what falls due until the next one lands, plus a buffer of counter sales (parts
sold to clients without a registered parlor), minus general-warehouse stock.

Who did a change: an invoice of the part with labor billed within LABOR_DAYS (a SERVICIO line with no description;
one with a description is a part sold under the generic code) is our crew's; without labor, the client or a third
party installed what they bought from us, and it shows as done by someone else. The registry grows from the same
invoices (sync_parlors, infer_parlors).

A part's relevance for a client (its order in the client's detail): how much the client buys of it a year (volume
times frequency, in pesos), weighted by how often it was changed on time, over the last RELEVANCE_YEARS.
"""

import math
import re
import statistics
import unicodedata
from collections import defaultdict
from datetime import date, timedelta

from django.core.cache import cache
from django.db import connections, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from api.services import FACTURA_DOC_TYPE, GENERAL_WAREHOUSE_ID, _gea_products

MONTH_DAYS = 30.44
MERGE_DAYS = 45            # purchases this close together are one change
MAX_GAP_MONTHS = 36        # a longer gap = bought elsewhere, not a replacement cycle
MIN_CLIENTS = 3            # fewer clients than this is no basis for a cross-client interval
STALE_MONTHS = 24          # no invoice of the part for this long: assume bought elsewhere; left out of the order
STALE_GRACE_MONTHS = 6     # a part with a longer interval gets it plus this before it counts as bought elsewhere
BUFFER_MONTHS = 2          # counter-sales stock on hand, about the order cycle plus transit
HISTORY_DAYS = 8 * 365
RELEVANCE_YEARS = 3
ORDER_WEEKDAY = 2          # Wednesday: GEA takes the order on the month's first one
CACHE_SECONDS = 600
LABOR_CODES = ('0000', '0004')  # SERVICIO, SERVICIO DE EMERGENCIA
LABOR_DAYS = 30            # labor this close to a part's invoice installed it (liners and labor often go on separate invoices)
LINER_MIN = 8              # fewer liners than this is a top-up, not a parlor's change
LINERS_PER_STALL = 4
REPEAT_CHANGES = 3         # bought this many times at a steady rhythm without our labor: still a service item


def base_code(code):
    """GEA parts are sold under letter-suffixed codes too (7021-2764-010W): one part."""
    return re.sub(r'(?<=\d)[A-Z]$', '', code.strip().upper())


def month_start(d):
    return date(d.year, d.month, 1)


def add_months(d, n):
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def order_day(today):
    """The next GEA order day on or after today: the first ORDER_WEEKDAY of this month, else of next month's."""
    for month in (month_start(today), add_months(month_start(today), 1)):
        day = month + timedelta(days=(ORDER_WEEKDAY - month.weekday()) % 7)
        if day >= today:
            return day


def months_between(a, b):
    return (b - a).days / MONTH_DAYS


def merge_purchases(lines):
    """[(client, code, day, qty[, invoice id])] -> {(client, code): [[day, qty, invoice id], ...]}, purchases
    within MERGE_DAYS of a window's first one merged (dated and identified by that first invoice). The window
    doesn't slide: purchases a month apart all year long are several changes, not one dated at the first."""
    by_key = defaultdict(list)
    for client, code, day, qty, *doc in sorted(lines, key=lambda r: r[2]):
        if qty <= 0:
            continue
        events = by_key[(client, code)]
        if events and (day - events[-1][0]).days <= MERGE_DAYS:
            events[-1][1] += qty
        else:
            events.append([day, qty, doc[0] if doc else None])
    return dict(by_key)


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
        gap = median_gap(full_changes(events, max(e[1] for e in events) / 2))
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


def interval(rule, hours_per_day, own, cross, sheet=None):
    """(months, basis) for one parlor part: GEA's rule, else the client's rhythm, else other clients', else the
    calendar's own RECAMBIO (sheet)."""
    if rule:
        return gea_months(rule, hours_per_day), 'GEA'
    return next(((m, basis) for m, basis in ((own, 'cliente'), (cross, 'clientes'), (sheet, 'calendario')) if m),
                (None, None))


def part_events(changes, months, today, start, end):
    """What the agenda shows for one part between start and end: [(day, kind)] with kind
    'done' (a change, i.e. an invoice), 'missed' (came due and wasn't changed that month) or 'due' (to come).
    Past due dates follow each change by the part's interval; after the last change, an overdue part is missed
    once, an up-to-date one repeats its interval until end."""
    ym = lambda d: (d.year, d.month)  # noqa: E731
    events = [(d, 'done') for d in changes]
    if months and changes:
        step = timedelta(days=months * MONTH_DAYS)
        for a, b in zip(changes, changes[1:]):
            if ym(b) > ym(a + step):
                events.append((a + step, 'missed'))
        due = changes[-1] + step
        if ym(due) < ym(today):
            events.append((due, 'missed'))
        else:
            while due <= end:
                events.append((due, 'due'))
                due += step
    return sorted((d, kind) for d, kind in events if start <= d <= end)


def own_purchases(events, qty, quantities):
    """A part a parlor has in several places (the green milk hose on the claws, 272 m, and on the LECC, 56 m):
    a purchase covering at least half of all of them changes them all; a smaller one, the largest place it covers
    by at least half (50 m is the LECC's). quantities: the part's quantity in each place."""
    if len(quantities) == 1:
        return events
    return [e for e in events if e[1] >= sum(quantities) / 2
            or max((q for q in quantities if e[1] >= q / 2), default=None) == qty]


def with_labor(day, labor_days):
    return any(abs((d - day).days) <= LABOR_DAYS for d in labor_days)


def due_rows(parlors, purchases, rules, cross, today, labor=None):
    """One row per parlor part (per place in the parlor) with its last change, interval and due date.

    parlors: [{'id', 'client', 'hours_per_day', 'parts': [(code, qty, group)], 'sheet_months'?: {(code, group):
    months}}]; purchases: merge_purchases(); rules: {code: (hours, months)}; cross: {code: months}; labor:
    {client: [days of billed labor]}, without it every invoiced change is ours.
    """
    rows = []
    for p in parlors:
        places = defaultdict(list)
        for code, qty, _ in p['parts']:
            places[code].append(qty)
        for code, qty, group in p['parts']:
            mine = own_purchases(purchases.get((p['client'], code), []), qty, places[code])
            # Changes someone else made (ExternalChange) restart the interval like ours; no invoice records them.
            external = dict(p.get('external', {}).get((code, group), []))
            changes = sorted(full_changes(mine, qty / 2) + [[d, qty, None] for d in external], key=lambda c: c[0])
            last, last_invoice = (changes[-1][0], changes[-1][2]) if changes else (None, None)
            months, basis = interval(rules.get(code), p['hours_per_day'], median_gap(changes), cross.get(code),
                                     p.get('sheet_months', {}).get((code, group)))
            due = last + timedelta(days=months * MONTH_DAYS) if last and months else None
            if last is None:
                status = 'unknown'
            elif months_between(last, today) > max(STALE_MONTHS, (months or 0) + STALE_GRACE_MONTHS):
                status = 'stale'
            elif due is None:
                status = 'no_interval'  # invoiced, but no GEA rule and too few changes to tell its rhythm
            elif due < today:
                status = 'overdue'
            else:
                status = 'ok'
            # The agenda spans two years back to the end of next year.
            invoices = {c[0]: c[2] for c in changes}
            ours = lambda d: labor is None or with_labor(d, labor.get(p['client'], []))  # noqa: E731
            events = part_events([c[0] for c in changes], months, today, date(today.year - 2, 1, 1),
                                 date(today.year + 1, 12, 31))
            rows.append({'parlor': p['id'], 'client': p['client'], 'code': code, 'quantity': qty, 'group': group,
                         'last_change': last, 'last_invoice': last_invoice,
                         'months': round(months, 1) if months else None, 'basis': basis,
                         'due': due, 'status': status,
                         # A change's invoice, to open it from the agenda; one made by someone else is 'external'
                         # (with its record's id, to undo it).
                         # An invoiced change with no labor of ours near it was installed by someone else too.
                         'events': [{'date': d, 'kind': 'external' if k == 'done' and (
                                         (d in external and not invoices.get(d)) or (invoices.get(d) and not ours(d)))
                                     else k, 'invoice': invoices.get(d) if k == 'done' else None,
                                     'external': external.get(d) if k == 'done' else None} for d, k in events]})
    return rows


def plannable(row):
    return row['due'] is not None and row['status'] != 'stale'


# The calendars name one group several ways; each part's category is the group's clean name. In this order
# on the page, roughly following the milk from the cow to the tank, then the vacuum and wash systems.
CATEGORIES = {
    'Colectores': ('COLECTORES', 'JUEGOS DE ORDENO'),
    'Pulsadores': ('PULSADORES',),
    'Vaso pesador': ('VASO PESADOR', 'VASO METATRON'),
    'Banco de válvulas': ('BANCO DE VALVULAS', 'VALVULA METATRON'),
    'Retiradores': ('RETIRADOR', 'RETIRADORES'),
    'Recibidor de leche': ('RECIBIDOR DE LECHE', 'RECIBIDOR', 'RECIBO', 'RECIBO DE LECHE', 'GRUPO DE RECIBO',
                           'TINA DE BALANCE'),
    'Bomba de leche': ('BOMBA DE LECHE', 'BOMBA DE LECHE (PENDIENTE DE USO)'),
    'Trampa de líquidos': ('TRAMPA DE LIQUIDOS', 'KIT TRAMPA DE LIQUIDOS'),
    'Regulador de vacío': ('REGULADOR DE VACIO',),
    'Sistema de vacío': ('SISTEMA DE VACIO', 'SISTEMA DE LUBRICACION Y BOMBA DE VACIO'),
    'Lavado': ('DISPOSITIVO DE LAVADO', 'INYECTOR', 'INYECTOR DE LAVADO', 'COMPASS PLUS', 'COMPASS PLUSS', 'LECC'),
    'Enfriamiento': ('CHILLER',),
    'Arreador': ('ARREADOR',),
    'Pediluvio': ('PEDILUVIO',),
}
_CATEGORY_OF = {name: category for category, names in CATEGORIES.items() for name in names}


def category(section):
    """A calendar section's category ("JUEGOS DE ORDEÑO" -> "Colectores"); an unknown one keeps its own name."""
    key = fold(section).strip()
    return _CATEGORY_OF.get(key, (section or '').strip().capitalize() or 'Otras')


def fold(text):
    return unicodedata.normalize('NFD', text or '').encode('ascii', 'ignore').decode().upper()


def part_family(code, erp_name, gea):
    """Parts that do the same job in a parlor, so a parlor has one of them: a parlor uses one liner, one long
    milk hose, one double vacuum hose. From GEA's category and description where it has the part (GEA calls
    7021-7101-030 a short milk tube though the ERP names it "TUBO LARGO"), else the ERP name (GEA has no data
    on most liners). A unit's complete and partial service kits are one family too (kit_family). Any other part
    is its own family."""
    path = fold(' '.join(gea.get('path') or []))
    desc = fold(gea.get('desc'))
    name = fold(erp_name)
    if kit_family(gea.get('desc')):
        return kit_family(gea.get('desc'))
    # The liner itself, not what goes with it (liner shells, plugs, sight glasses, LECC rings).
    if name.startswith('PEZONERA') or re.match(r'^([A-Z]+ - )?(GOMA )?PEZONERA', desc):
        return 'pezonera'
    # Not a hose the ERP calls a vacuum hose: GEA files 4999-1090-160 ("MANGUERA DE VACIO SIMPLE GOMA 9/16"",
    # a wash-line hose in the calendars) as a milk hose, which would make a parlor's milk hose ambiguous.
    if 'VACIO' not in name and ('TUBOS DE LECHE LARGOS' in path or desc.startswith(('MANGUERA DE LECHE', 'MANGA DE LECHE'))):
        return 'manguera de leche'
    if 'VACIO DOBLE' in name or 'DOBLE DE VACIO' in desc:  # a single vacuum hose is another part
        return 'manguera de vacio doble'
    return code


KIT_RE = re.compile(r'^(JUEGO DE SERVICIO|KIT DE SERVICIO|KIT PARA SERVICIO TECNICO) - (.*?)\s*\((C|P)\)\s*(.*)$')


def kit_family(gea_desc):
    """GEA names a unit's complete and partial service kits alike but for (C)/(P) ("Juego de servicio -
    Pulsation (C) StimoPuls/AutoPuls Apex"): one row in the plan, dated by the latest of either. None for
    anything else."""
    m = KIT_RE.match(fold(gea_desc))
    return f'kit: {m[2]} {m[4]}'.strip() if m else None


def family_mates(codes, families):
    """{code: [the other products of its family]} for the codes in a family. families: {code: family} for every
    product that can be invoiced."""
    by_family = defaultdict(set)
    for code, family in families.items():
        if family != code:
            by_family[family].add(code)
    return {code: sorted(by_family[families[code]] - {code})
            for code in codes if families.get(code, code) != code and len(by_family[families[code]]) > 1}


def alias_family(lines, parlors, families, mates):
    """Invoices of a part's family mates count as the part the parlor has registered (the other kit of a unit, a
    hose in another roll size or material, another liner), for that parlor's client only, and only when the
    parlor has one part of that family: with two (a cluster hose and a wash hose) an invoice can't say which."""
    alias = {}
    for p in parlors:
        registered = {code for code, *_ in p['parts']}
        count = defaultdict(int)
        for code in registered:
            count[families.get(code, code)] += 1
        for code in registered:
            if count[families.get(code, code)] == 1:
                for mate in mates.get(code, []):
                    alias[(p['client'], mate)] = code
    return [(client, alias.get((client, code), code), *rest) for client, code, *rest in lines]


def product_key(name):
    """A product's name without packaging in parentheses, a closing "SUST" (a substitute for the GEA original),
    accents, punctuation or spacing: two ERP codes with the same key are one product sold under two codes
    (C300-11 "BOLA DE CIERRE COLECTOR CLASSIC 300 SUST" stands for 7009-2786-020; 7750-0220-527/-528 are one
    hose in a 100 ft and a 500 ft roll). "SUSTITUTO DE LECHE" (milk replacer) keeps its word: it's not at the end."""
    name = re.sub(r'\bSUST(ITUTO)?\s*$', '', fold(re.sub(r'\([^)]*\)', '', name or '')).strip())
    return re.sub(r'[^A-Z0-9]', '', name)


def same_products(codes, names):
    """{code: [other ERP codes of the same product]} for the codes that have any."""
    by_key = defaultdict(set)
    for code, name in names.items():
        if product_key(name):
            by_key[product_key(name)].add(code)
    return {c: sorted(by_key[product_key(names[c])] - {c}) for c in codes
            if c in names and len(by_key[product_key(names[c])]) > 1}


def alias_same_product(lines, parlors, same):
    """Invoices of the same product under another code count as the code the client's parlor registers. Unlike
    family mates (alias_family) this applies even when the parlor has other parts of the family: it's one product."""
    alias = {}
    for p in parlors:
        for code, *_ in p['parts']:
            for other in same.get(code, []):
                alias.setdefault((p['client'], other), code)
    return [(client, alias.get((client, code), code), *rest) for client, code, *rest in lines]


# Sizes (16 X 2, 9/16", 51MM, 90°) tell two sizes of one part apart; the other numbers name a model (VACUREX
# 5000/1200, BALERO 6306/6307, RPS 600-1200/1500-2800, P1200).
SIZE_RE = re.compile(r'\d+(\.\d+)?\s*X\s*\d+(\.\d+)?(\s*X\s*\d+(\.\d+)?)*|\d+\s*/\s*\d+|\d+(\.\d+)?\s*(MM|CM|M|°|")|[½¼¾°"]')
NAME_STOP = {'DE', 'DEL', 'LA', 'EL', 'LOS', 'LAS', 'PARA', 'CON', 'Y', 'X', 'CPL', 'GEA', 'JGO', 'JUEGO'}


def name_parts(name):
    """(words, model numbers, sizes) of an ERP name, without what's in parentheses (packaging)."""
    name = fold(re.sub(r'\([^)]*\)', ' ', name or ''))
    sizes = frozenset(re.sub(r'\s+', '', m[0]) for m in SIZE_RE.finditer(name))
    rest = SIZE_RE.sub(' ', name)
    tokens = re.findall(r'[A-Z0-9]+(?:[.-][A-Z0-9]+)*', rest)
    words = frozenset(t for t in tokens if t.isalpha() and len(t) > 1 and t not in NAME_STOP)
    numbers = frozenset(t for t in tokens if any(ch.isdigit() for ch in t))
    return words, numbers, sizes


def same_part_other_model(code_a, name_a, code_b, name_b):
    """Two ERP products that are one part in another model, so a client who changes to one changed the other:
    the same words with a different model number (MEMBRANA VACUREX 5000 / MEMBRANA 1200 VACUREX), or sibling GEA
    codes whose names differ by one word at most (7161-9905-020 / -040, Apex or not; a 7330 / 7360 wash cup). Not
    a size apart (JUNTA ANULAR 16 X 2 / 16 X 3.5, hoses 9/16" / 9/32"): those are different parts of one parlor.
    One product under two codes is same_products' job."""
    wa, na, sa = name_parts(name_a)
    wb, nb, sb = name_parts(name_b)
    if len(wa & wb) < 2 or product_key(name_a) == product_key(name_b):
        return False
    siblings = len(code_a) == len(code_b) > 4 and code_a[:-3] == code_b[:-3]
    if wa == wb and na != nb:
        return True
    return siblings and len(wa ^ wb) <= 1 and (na != nb or sa == sb)


def model_variants(codes, names):
    """{code: [other ERP products that are the same part in another model]} for the codes that have any."""
    parsed = {c: name_parts(n) for c, n in names.items()}
    by_word = defaultdict(set)
    for c, (words, _, _) in parsed.items():
        for w in words:
            by_word[w].add(c)
    variants = {}
    for code in codes:
        if code not in names:
            continue
        words = parsed[code][0]
        near = {c for w in words for c in by_word[w]} - {code}
        found = sorted(c for c in near if same_part_other_model(code, names[code], c, names[c]))
        if found:
            variants[code] = found
    return variants


def swap_options(parlors, variants, mates, families, same):
    """{(parlor id, code): [products the parlor may have instead]}: other models of the part (model_variants) and,
    where the parlor registers no other part of its family, the family's other products (the green silicone milk
    hose for the transparent one). Not the other kit of a unit (complete and partial kits alternate: alias_family
    keeps them one row), nor the same product under another code (alias_same_product)."""
    options = {}
    for p in parlors:
        count = defaultdict(int)
        registered = {code for code, *_ in p['parts']}
        for code in registered:
            count[families.get(code, code)] += 1
        for code in registered:
            family = families.get(code, code)
            mine = set(variants.get(code, []))
            if count[family] == 1 and not family.startswith('kit:'):
                mine |= set(mates.get(code, []))
            if mine - set(same.get(code, [])):
                options[(p['id'], code)] = sorted(mine - set(same.get(code, [])))
    return options


def model_swaps(parlors, purchases, options):
    """{(parlor id, code): the model the client changed to}: a registered part whose client's latest change (a
    purchase of at least half the parlor's quantity) is of another model of it, newer than any change of the
    registered one, and that the parlor doesn't register too. The calendar listed one model; the invoices say
    which one the parlor has. options: swap_options()."""
    swaps = {}
    for p in parlors:
        registered = {code for code, *_ in p['parts']}
        for code, qty, _ in p['parts']:
            own = full_changes(purchases.get((p['client'], code), []), qty / 2)
            since = own[-1][0] if own else date.min
            latest = {v: ch[-1][0] for v in options.get((p['id'], code), []) if v not in registered
                      and (ch := full_changes(purchases.get((p['client'], v), []), qty / 2))}
            best = max(latest, key=latest.get, default=None)
            if best and latest[best] > since:
                swaps[(p['id'], code)] = best
    return swaps


def apply_swaps(parlors, lines, swaps):
    """The parlors with each swapped part under the model the client buys (keeping its quantity, group and
    calendar interval, and 'registered_as' the calendar's code), and the client's invoices of the old model
    counted as the new one: they were the same position in the parlor."""
    by_client = {}
    out = []
    for p in parlors:
        mine = {old: new for (pid, old), new in swaps.items() if pid == p['id']}
        for old, new in mine.items():
            by_client[(p['client'], old)] = new
        rename = lambda c: mine.get(c, c)  # noqa: E731
        out.append({**p, 'parts': [(rename(c), q, g) for c, q, g in p['parts']],
                    'sheet_months': {(rename(c), g): m for (c, g), m in p.get('sheet_months', {}).items()},
                    'ids': {(rename(c), g): i for (c, g), i in p.get('ids', {}).items()},
                    'external': {(rename(c), g): e for (c, g), e in p.get('external', {}).items()},
                    'registered_as': {new: old for old, new in mine.items()}})
    return out, [(client, by_client.get((client, code), code), *rest) for client, code, *rest in lines]


def kit_contents(codes, gea_products):
    """{assembly code: [registered codes it contains]} from GEA's parts and spare-parts lists: buying the whole
    assembly (a complete float switch) changes the parts inside it (its float)."""
    contents = defaultdict(set)
    for kit, entry in gea_products.items():
        for item in (entry.get('parts') or []) + (entry.get('spare_parts') or []):
            inner = base_code(item.get('code') or '')
            if inner in codes and inner != kit:
                contents[kit].add(inner)
    return {kit: sorted(inner) for kit, inner in contents.items()}


def expand_kits(lines, parlors, contents):
    """Adds, for a client whose parlor registers a part, an invoice line of that part for each assembly bought
    that contains it (same day, quantity and invoice; no amount, which stays on the assembly). Whether it counts
    as a change is still decided by quantity (full_changes): two claw shells for eight claws don't."""
    registered = {(p['client'], code) for p in parlors for code, *_ in p['parts']}
    extra = [(client, inner, day, qty, doc, 0.0) for client, code, day, qty, doc, *_ in lines
             for inner in contents.get(code, []) if (client, inner) in registered]
    return lines + extra


def one_per_family(parts, families, last_invoice):
    """parts: [(group, code, qty)] in the calendar's order -> (kept, dropped). Within one calendar group (where
    the part goes), keeps one part per family: the one invoiced to the client most recently, else the first
    listed. families: {code: family}; last_invoice: {code: day}."""
    chosen = {}
    for i, (group, code, qty) in enumerate(parts):
        key = (group, families.get(code, code))
        rank = (last_invoice.get(code) or date.min, -i)
        if key not in chosen or rank > chosen[key][0]:
            chosen[key] = (rank, (group, code, qty))
    kept = [part for _, part in chosen.values()]
    return kept, [part for part in parts if part not in kept]


def what_they_buy(kept, families, purchases):
    """Swaps a kept liner for the liner the client changed to most recently, when that's a different one (a
    calendar can list a liner the client no longer buys, or a code that isn't in the ERP). Only liners: a parlor
    has one liner position, while hoses of one family go to several places (cluster, wash, LECC) and an invoice
    doesn't say which. A change = a purchase of at least half the parlor's quantity (merge_purchases events).
    kept: [(group, code, qty)]; purchases: {code: [[day, qty], ...]} for the client -> (parts, [(old, new)])."""
    parts, swaps = [], []
    for group, code, qty in kept:
        if families.get(code) == 'pezonera':
            changes = {c: full_changes(ev, qty / 2)[-1][0] for c, ev in purchases.items()
                       if families.get(c) == 'pezonera' and full_changes(ev, qty / 2)}
            best = max(changes, key=changes.get, default=code)
            if best != code and changes[best] > changes.get(code, date.min):
                swaps.append((code, best))
                code = best
        parts.append((group, code, qty))
    return parts, swaps


def relevance(events, yearly_value, today):
    """How much a part matters in a client's detail: {'per_year': changes a year, 'on_time': share of the times it
    came due that it was changed in its month (None without any), 'score': pesos a year times that share}, over
    the last RELEVANCE_YEARS. A part never changed late keeps its whole value; one usually skipped sinks."""
    since = today - timedelta(days=RELEVANCE_YEARS * 365)
    recent = [k for d, k in events if since <= d <= today]
    done, missed = recent.count('done'), recent.count('missed')
    on_time = done / (done + missed) if done + missed else None
    return {'per_year': round(done / RELEVANCE_YEARS, 1), 'on_time': round(on_time, 2) if on_time is not None else None,
            'score': round(yearly_value * (on_time if on_time is not None else 0.5))}


def counter_monthly(lines, registered_clients, today):
    """{code: units a month} sold over the last 12 months to clients without a registered parlor."""
    since = today - timedelta(days=365)
    units = defaultdict(float)
    for client, code, day, qty, *_ in lines:
        if day >= since and client not in registered_clients:
            units[code] += qty
    return {code: u / 12 for code, u in units.items()}


def order_proposal(rows, order_month, stock, counter):
    """What to order from GEA in `order_month`: parts falling due until the next order arrives (end of the
    following month, overdue ones too), plus BUFFER_MONTHS of counter sales, minus stock."""
    cover_until = add_months(order_month, 2)
    service = defaultdict(int)
    for r in rows:
        if plannable(r) and r['due'] < cover_until:
            service[r['code']] += r['quantity']
    lines = []
    for code in sorted(set(service) | {c for c, u in counter.items() if u > 0}):
        buffer = math.ceil(counter.get(code, 0) * BUFFER_MONTHS)
        need = service[code] + buffer - max(stock.get(code, 0), 0)
        if need > 0:
            lines.append({'code': code, 'services': service[code], 'buffer': buffer, 'stock': stock.get(code, 0),
                          'order': math.ceil(need)})
    return lines


# ---------- ERP reads (read-only), cached like the other ERP-backed pages

def fetch_invoice_lines(codes, since):
    """[(client code, base product code, day, units, invoice id, line total)] of invoices since `since` for these
    parts."""
    codes = sorted(codes)
    if not codes:
        return []
    key = f'maintenance_lines_v3_{since}_{hash(tuple(codes))}'
    rows = cache.get(key)
    if rows is None:
        likes = ' OR '.join(['p.CCODIGOPRODUCTO LIKE %s'] * len(codes))
        with connections['erp'].cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.CCODIGOCLIENTE, p.CCODIGOPRODUCTO, d.CFECHA, m.CUNIDADES, d.CIDDOCUMENTO, m.CTOTAL
                FROM admMovimientos m
                JOIN admDocumentos d ON d.CIDDOCUMENTO = m.CIDDOCUMENTO
                JOIN admProductos p ON p.CIDPRODUCTO = m.CIDPRODUCTO
                JOIN admClientes c ON c.CIDCLIENTEPROVEEDOR = d.CIDCLIENTEPROVEEDOR
                WHERE d.CIDDOCUMENTODE = %s AND d.CCANCELADO = 0 AND d.CFECHA >= %s AND ({likes})
                """,
                [FACTURA_DOC_TYPE, since, *[f'{c}%' for c in codes]],
            )
            wanted = set(codes)
            rows = [(client.strip(), base_code(code), day.date(), float(qty), doc, float(total))
                    for client, code, day, qty, doc, total in cursor.fetchall() if base_code(code) in wanted]
        cache.set(key, rows, CACHE_SECONDS)
    return rows


def fetch_labor_days(since):
    """{client code: sorted days} with labor invoiced: a SERVICIO line without a description."""
    key = f'maintenance_labor_v1_{since}'
    days = cache.get(key)
    if days is None:
        with connections['erp'].cursor() as cursor:
            cursor.execute(
                f"""
                SELECT DISTINCT c.CCODIGOCLIENTE, d.CFECHA
                FROM admMovimientos m
                JOIN admDocumentos d ON d.CIDDOCUMENTO = m.CIDDOCUMENTO
                JOIN admProductos p ON p.CIDPRODUCTO = m.CIDPRODUCTO
                JOIN admClientes c ON c.CIDCLIENTEPROVEEDOR = d.CIDCLIENTEPROVEEDOR
                WHERE d.CIDDOCUMENTODE = %s AND d.CCANCELADO = 0 AND d.CFECHA >= %s
                  AND p.CCODIGOPRODUCTO IN ({', '.join(['%s'] * len(LABOR_CODES))})
                  AND LTRIM(RTRIM(ISNULL(CAST(m.COBSERVAMOV AS nvarchar(max)), ''))) = ''
                """,
                [FACTURA_DOC_TYPE, since, *LABOR_CODES],
            )
            days = defaultdict(list)
            for client, day in cursor.fetchall():
                days[client.strip()].append(day.date())
            days = {c: sorted(d) for c, d in days.items()}
        cache.set(key, days, CACHE_SECONDS)
    return days


def fetch_products(codes):
    """({base code: units in the general warehouse}, {base code: name}, {base code: ERP product id = the
    catalog's key}); letter-suffixed codes of one part add up, the unsuffixed code names it when it exists."""
    if not codes:
        return {}, {}, {}
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            """
            SELECT p.CCODIGOPRODUCTO, p.CNOMBREPRODUCTO, p.CIDPRODUCTO, e.CENTRADASPERIODO12 - e.CSALIDASPERIODO12
            FROM admProductos p
            LEFT JOIN admExistenciaCosto e ON e.CIDPRODUCTO = p.CIDPRODUCTO AND e.CIDALMACEN = %s
              AND e.CIDEJERCICIO = (SELECT MAX(CIDEJERCICIO) FROM admExistenciaCosto WHERE CIDALMACEN = %s)
            """,
            [GENERAL_WAREHOUSE_ID, GENERAL_WAREHOUSE_ID],
        )
        stock, names, keys = defaultdict(float), {}, {}
        for code, name, product_id, units in cursor.fetchall():
            base = base_code(code)
            if base in codes:
                stock[base] += float(units or 0)
                if base == code.strip().upper() or base not in names:
                    names[base] = name.strip()
                    keys[base] = str(product_id)
    return {c: round(u, 2) for c, u in stock.items()}, names, keys


def fetch_all_names():
    """{base code: name} of every ERP product, to tell each part's family."""
    names = cache.get('maintenance_all_names_v1')
    if names is None:
        with connections['erp'].cursor() as cursor:
            cursor.execute('SELECT CCODIGOPRODUCTO, CNOMBREPRODUCTO FROM admProductos WHERE CIDPRODUCTO <> 0')
            names = {}
            for code, name in cursor.fetchall():
                names.setdefault(base_code(code), name.strip())
        cache.set('maintenance_all_names_v1', names, CACHE_SECONDS)
    return names


# GEA's catalog sections that aren't the milking parlor: teat dips, barn fans and mats, feed, collars.
NOT_PARLOR_SECTIONS = ('HIGIENE', 'HARDWARE DE HIGIENE', 'NEOGEN', 'BARN EQUIPMENT', 'PIEZAS PARA ALIMENTACION',
                       'DIGITAL SOLUTIONS')


def parlor_product(code, name, gea, calendar):
    """A product of the milking parlor's service: GEA's parlor parts and equipment (milking, pulsation, vacuum,
    milk meters, cooling), any liner, or a part a calendar lists; not hygiene, barn equipment, feed or other
    lines (Bionat)."""
    if code in calendar or fold(name).startswith('PEZONERA'):
        return True
    section = fold(((gea.get(code) or {}).get('path') or [''])[0]).strip(' -.')
    return bool(section) and not section.startswith(NOT_PARLOR_SECTIONS)


def fetch_client_sales(codes, since, gea, calendar):
    """{client code: invoiced since `since` in parlor service, IVA included}: parlor_product lines plus our labor
    (a SERVICIO line without a description), to sort the agenda by who our best service clients are. Invoices only
    (returns and credit notes aren't netted): a size, not an accounting figure."""
    if not codes:
        return {}
    key = f'maintenance_client_sales_v2_{since}_{hash(tuple(sorted(codes)))}_{hash(tuple(sorted(calendar)))}'
    sales = cache.get(key)
    if sales is None:
        with connections['erp'].cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.CCODIGOCLIENTE, p.CCODIGOPRODUCTO, p.CNOMBREPRODUCTO,
                       CASE WHEN LTRIM(RTRIM(ISNULL(CAST(m.COBSERVAMOV AS nvarchar(max)), ''))) = '' THEN 0 ELSE 1 END,
                       SUM(m.CTOTAL)
                FROM admMovimientos m
                JOIN admDocumentos d ON d.CIDDOCUMENTO = m.CIDDOCUMENTO
                JOIN admProductos p ON p.CIDPRODUCTO = m.CIDPRODUCTO
                JOIN admClientes c ON c.CIDCLIENTEPROVEEDOR = d.CIDCLIENTEPROVEEDOR
                WHERE d.CIDDOCUMENTODE = %s AND d.CCANCELADO = 0 AND d.CFECHA >= %s
                  AND c.CCODIGOCLIENTE IN ({', '.join(['%s'] * len(codes))})
                GROUP BY c.CCODIGOCLIENTE, p.CCODIGOPRODUCTO, p.CNOMBREPRODUCTO,
                         CASE WHEN LTRIM(RTRIM(ISNULL(CAST(m.COBSERVAMOV AS nvarchar(max)), ''))) = '' THEN 0 ELSE 1 END
                """,
                [FACTURA_DOC_TYPE, since, *codes],
            )
            sales = defaultdict(float)
            for client, code, name, described, total in cursor.fetchall():
                code = code.strip()
                if (code in LABOR_CODES and not described) or parlor_product(base_code(code), name, gea, calendar):
                    sales[client.strip()] += float(total or 0)
            sales = {c: round(t) for c, t in sales.items()}
        cache.set(key, sales, CACHE_SECONDS)
    return sales


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


# ---------- the registry from the invoices (sync_parlors)

def service_items(events, labor_days, liner, today):
    """The changes of one part for one client that make it one of the client's service items, or [] when it isn't:
    one with our labor in the last STALE_MONTHS, or REPEAT_CHANGES at a steady rhythm (the client or a third party
    installs them, and we want that business). A liner change is LINER_MIN liners or more; any other part's is at
    least half its largest purchase."""
    full = [e for e in events if e[1] >= (LINER_MIN if liner else max(e[1] for e in events) / 2)]
    recent = [e for e in full if months_between(e[0], today) <= STALE_MONTHS]
    if not recent:
        return []
    if any(with_labor(e[0], labor_days) for e in recent):
        return full
    return full if len(full) >= REPEAT_CHANGES and median_gap(full) is not None else []


def stalls_of(change):
    return int(change[1] // LINERS_PER_STALL)


def infer_parlors(purchases, labor, liners, registry, covered, today):
    """What the invoices add to the registry.

    purchases: merge_purchases() of the service items (every part on a calendar, and every liner); labor: {client:
    [days]}; liners: liner codes; registry: {client: [{'id', 'active', 'stalls', 'codes', 'liner', 'dismissed'}]}
    with 'liner' the parlor's liner code or None; covered(code, codes): the code is already one of these parts by
    family, product or model (the plan counts its invoices for them).

    Returns {'new': {client: {'stalls', 'parts': {code: qty}}}, 'add': [(parlor id, code, qty)],
    'stalls': [(parlor id, old, new)]}: a new parlor for a client with service items and none registered; parts a
    client's only parlor is missing; a stall count the last two liner changes (of the last STALE_MONTHS, with
    liners among the client's service items) agree on and the parlor doesn't (the calendars' counts are sometimes
    wrong). The stalls come from the liners: LINERS_PER_STALL each; a parlor without liners has 0.
    """
    items = defaultdict(dict)
    for (client, code), events in purchases.items():
        changes = service_items(events, labor.get(client, []), code in liners, today)
        if changes:
            items[client][code] = changes
    out = {'new': {}, 'add': [], 'stalls': []}
    for client, found in items.items():
        # One liner per parlor: the one changed last.
        liner_codes = sorted((c for c in found if c in liners), key=lambda c: found[c][-1][0])
        for c in liner_codes[:-1]:
            del found[c]
        liner = liner_codes[-1] if liner_codes else None
        parlors = registry.get(client, [])
        if not parlors:
            stalls = stalls_of(found[liner][-1]) if liner else 0
            out['new'][client] = {'stalls': stalls, 'parts': {
                c: stalls * LINERS_PER_STALL if c == liner else round(ch[-1][1]) for c, ch in found.items()}}
            continue
        if len(parlors) > 1 or not parlors[0]['active']:
            continue  # which parlor a purchase is for can't be told; a deactivated one stays so
        p = parlors[0]
        for c, ch in found.items():
            if c not in p['dismissed'] and c not in p['codes'] and not covered(c, p['codes']):
                out['add'].append((p['id'], c, stalls_of(ch[-1]) * LINERS_PER_STALL if c == liner else round(ch[-1][1])))
        # Every liner the client changed lately counts for the stall count, whatever its model.
        changes = sorted((e for c in liners for e in purchases.get((client, c), [])
                          if e[1] >= LINER_MIN and months_between(e[0], today) <= STALE_MONTHS), key=lambda e: e[0])
        if liner and len(changes) >= 2 and stalls_of(changes[-1]) == stalls_of(changes[-2]) != p['stalls']:
            out['stalls'].append((p['id'], p['stalls'], stalls_of(changes[-1])))
    return out


# ---------- the plan, from the local registry plus live ERP data

def build_plan(today):
    from .models import Parlor

    contacted = {p.id: (p.contacted_at, p.contacted_by) for p in Parlor.objects.filter(contacted_at__isnull=False)
                 .select_related('contacted_by')}
    parlors = [{'id': p.id, 'client': p.client_code, 'label': p.label, 'hours_per_day': p.milking_hours_per_day,
                'parts': [(x.code, x.quantity, x.group) for x in p.parts.all()],
                'sheet_months': {(x.code, x.group): x.sheet_months for x in p.parts.all() if x.sheet_months},
                'ids': {(x.code, x.group): x.id for x in p.parts.all()},
                'external': {(x.code, x.group): [(e.day, e.id) for e in x.external_changes.all()] for x in p.parts.all()}}
               for p in Parlor.objects.filter(active=True).prefetch_related('parts__external_changes')]
    registered = {code for p in parlors for code, *_ in p['parts']}
    gea = {base_code(k): v for k, v in _gea_products().items()}
    all_names = fetch_all_names()
    variants = model_variants(registered, all_names)
    # Every model a part could be swapped to, so its family, same-product and assembly invoices are read too.
    candidates = registered | {v for vs in variants.values() for v in vs}
    families = {c: part_family(c, name, gea.get(c, {})) for c, name in all_names.items()}
    mates = family_mates(candidates, families)
    same = same_products(candidates, all_names)
    contents = kit_contents(candidates, gea)
    related = {m for ms in list(mates.values()) + list(same.values()) for m in ms} | set(contents)
    lines = fetch_invoice_lines(candidates | related, today - timedelta(days=HISTORY_DAYS))
    options = swap_options(parlors, variants, mates, families, same)
    parlors, lines = apply_swaps(parlors, lines, model_swaps(parlors, merge_purchases(lines), options))
    codes = {code for p in parlors for code, *_ in p['parts']}
    lines = alias_same_product(lines, parlors, same)
    lines = alias_family(lines, parlors, families, mates)
    lines = expand_kits(lines, parlors, contents)
    purchases = merge_purchases(lines)
    rules, cross = gea_rules(codes), cross_client_months(purchases)
    labor = fetch_labor_days(today - timedelta(days=HISTORY_DAYS))
    rows = due_rows(parlors, purchases, rules, cross, today, labor)

    # Our crew billed labor this year: a client we serve. The rest are prospects: their parts aren't ordered as
    # services, and what they buy counts as counter sales.
    attended = {p['client'] for p in parlors if any(d.year == today.year for d in labor.get(p['client'], []))}
    stock, names, keys = fetch_products(codes)
    # Only registered parts: the family mates fetched above are other products, not ones to order for a parlor.
    counter = {code: v for code, v in counter_monthly(lines, attended, today).items() if code in codes}
    next_order = order_day(today)
    order = order_proposal([r for r in rows if r['client'] in attended], month_start(next_order), stock, counter)
    since = today - timedelta(days=RELEVANCE_YEARS * 365)
    spent = defaultdict(float)
    for client, code, day, _, _, total in lines:
        if day >= since:
            spent[(client, code)] += total

    clients = fetch_clients({p['client'] for p in parlors})
    phones = fetch_client_phones({p['client'] for p in parlors})
    sales = fetch_client_sales({p['client'] for p in parlors}, today - timedelta(days=365), gea,
                               {code for p in parlors for code, *_ in p['parts']})
    quoted = quoted_places([p['id'] for p in parlors])
    by_id = {p['id']: p for p in parlors}
    by_parlor = defaultdict(list)
    for r in rows:
        p = by_id[r['parlor']]
        events = [(e['date'], e['kind']) for e in r['events']]
        quote = quoted.get((r['parlor'], r['code'], r['group']))
        by_parlor[r['parlor']].append({**r, 'id': p['ids'][(r['code'], r['group'])],
                                       # A quote made after the last change: the part is on its way to being done.
                                       'quote': quote[1] if quote and (not r['last_change'] or quote[0] > r['last_change'])
                                       else None,
                                       'registered_as': p['registered_as'].get(r['code']), **relevance(
            events, spent[(r['client'], r['code'])] / RELEVANCE_YEARS, today)})
    return {
        'categories': list(CATEGORIES),
        'names': names,
        'keys': keys,
        'stock': stock,  # general warehouse
        'prices': catalog_prices(keys),
        'parlors': [{**{k: p[k] for k in ('id', 'client', 'label', 'hours_per_day')},
                     'client_id': clients.get(p['client'], (None, ''))[0],
                     'name': clients.get(p['client'], (None, ''))[1],
                     'sales_12m': sales.get(p['client'], 0),
                     'attended': p['client'] in attended,
                     'phone': phones.get(p['client'], ''),
                     # A prospect someone reached out to: by hand, or by quoting them.
                     'contacted_at': contacted.get(p['id'], (None,))[0],
                     'contacted_by': (lambda u: u and (u.get_full_name() or u.username))(contacted.get(p['id'], (None, None))[1]),
                     # The prospects list puts the ones with a part due soon first.
                     # Quotes the client approved that aren't invoiced yet (kept when a prospect's parts are left out).
                     'accepted_quotes': sorted({r['quote']['id'] for r in by_parlor[p['id']]
                                                if r['quote'] and r['quote']['status'] == 'aceptado'}),
                     'next_due': min((r['due'] for r in by_parlor[p['id']] if r['status'] in ('ok', 'overdue')), default=None),
                     'parts': sorted(by_parlor[p['id']], key=lambda r: (r['due'] is None, r['due'] or today))}
                    for p in parlors],
        'order': {'day': next_order, 'lines': order},
        'invoiced_quotes': invoiced_quotes(rows),
    }


def invoiced_quotes(rows):
    """Ids of shared Servicios quotes whose every part has an invoice of ours (with or without our labor) on or after
    the day it was quoted: the sale went through, so the nightly sync closes them."""
    from .models import ServiceQuote

    done = defaultdict(list)
    for r in rows:
        done[(r['parlor'], r['code'], r['group'])] += [e['date'] for e in r['events'] if e['invoice']]
    out = []
    for q in ServiceQuote.objects.filter(request__status='APPROVED'):
        day = timezone.localdate(q.created_at)
        if q.places and all(any(d >= day for d in done[(q.parlor_id, code, group)]) for code, group in q.places):
            out.append(q.request_id)
    return out


# ---------- a service quote: the parts staff pick in a client's detail, as a quote request (catalog.quotes)

def valid_phone(phone):
    return sum(c.isdigit() for c in phone or '') >= 10


def fetch_client_phones(codes):
    """{client code: phone}: the one staff typed (ClientPhone), else Contpaqi's first on file."""
    from .models import ClientPhone

    codes = sorted(codes)
    if not codes:
        return {}
    phones = {}
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            f"""
            SELECT c.CCODIGOCLIENTE, d.CTELEFONO1, d.CTELEFONO2
            FROM admClientes c
            JOIN admDomicilios d ON d.CIDCATALOGO = c.CIDCLIENTEPROVEEDOR AND d.CTIPOCATALOGO = 1
            WHERE c.CCODIGOCLIENTE IN ({', '.join(['%s'] * len(codes))})
            ORDER BY d.CTIPODIRECCION
            """,
            codes,
        )
        for code, *numbers in cursor.fetchall():
            phones.setdefault(code.strip(), next((n.strip()[:30] for n in numbers if n and n.strip()), None))
    phones = {c: p for c, p in phones.items() if p}
    phones.update(ClientPhone.objects.filter(client_code__in=codes).values_list('client_code', 'phone'))
    return phones


def save_client_phone(client_code, phone, user):
    """Keeps a client's phone and fixes it on their open quotes from Servicios that have none that works."""
    from catalog.models import QuoteRequest
    from catalog.quotes import QuoteError, _log

    from .models import ClientPhone

    phone = str(phone or '').strip()
    if len(phone) > 30 or not valid_phone(phone):
        raise QuoteError('Revisa el teléfono (10 dígitos).')
    ClientPhone.objects.update_or_create(client_code=client_code, defaults={'phone': phone, 'updated_by': user})
    for req in QuoteRequest.objects.filter(service_quote__parlor__client_code=client_code,
                                           status__in=(QuoteRequest.STATUS_NEW, QuoteRequest.STATUS_CONTACTED,
                                                       QuoteRequest.STATUS_APPROVED)):
        if not valid_phone(req.phone):
            req.phone = phone
            req.save(update_fields=['phone'])
            _log(req, user, f'puso el teléfono del cliente: {phone}')
    return phone


def fetch_client_contact(client_code):
    """(name, phone) of an ERP client: the phone staff typed (ClientPhone), else the first on file."""
    from .models import ClientPhone
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            """
            SELECT c.CRAZONSOCIAL, d.CTELEFONO1, d.CTELEFONO2
            FROM admClientes c
            LEFT JOIN admDomicilios d ON d.CIDCATALOGO = c.CIDCLIENTEPROVEEDOR AND d.CTIPOCATALOGO = 1
            WHERE c.CCODIGOCLIENTE = %s
            ORDER BY d.CTIPODIRECCION
            """,
            [client_code],
        )
        rows = cursor.fetchall()
    if not rows:
        return None, ''
    phone = next((p.strip() for r in rows for p in r[1:] if p and p.strip()), '')
    local = ClientPhone.objects.filter(client_code=client_code).values_list('phone', flat=True).first()
    return rows[0][0].strip(), (local or phone)[:30]


def catalog_prices(keys):
    """{base code: list price, IVA included} from the catalog, which staff already see on a request's page."""
    from api.services import _catalog

    price = {p['key']: p.get('price') for p in _catalog(True)}
    return {code: price[key] for code, key in keys.items() if price.get(key)}


QUOTE_STATUS = {'NEW': 'cotizado', 'CONTACTED': 'cotizado', 'APPROVED': 'aprobado'}


def quoted_places(parlor_ids):
    """{(parlor id, code, group): (day quoted, {'id', 'status'})}: each part's latest service quote that wasn't
    closed (status: cotizado, aprobado = shared on the client's link, enviado, aceptado = the client approved it)."""
    from .models import ServiceQuote

    out = {}
    for q in (ServiceQuote.objects.filter(parlor_id__in=parlor_ids).exclude(request__status='REJECTED')
              .select_related('request').order_by('created_at')):
        r = q.request
        status = 'aceptado' if r.accepted_at else 'enviado' if r.sent_at else QUOTE_STATUS[r.status]
        for code, group in q.places:
            out[(q.parlor_id, code, group)] = (timezone.localdate(q.created_at), {'id': q.request_id, 'status': status})
    return out


def create_service_quote(parlor, items, user):
    """A quote request for the parts picked in a parlor's detail (items: [{'key': catalog key, 'quantity', 'code',
    'group'}], code and group naming the part's place in the parlor), owned by whoever made it, for the client on
    file: it then follows the Solicitudes flow (prices, approval, the client's link) like any other request, and
    the agenda shows those parts as quoted."""
    from api.services import _catalog
    from catalog.models import QuoteRequest, QuoteRequestItem
    from catalog.quotes import QuoteError, _clean_items, _log

    from .models import Parlor, ServiceQuote

    code_by_key = {p['key']: p['CCODIGOPRODUCTO'] for p in _catalog(True)}
    cleaned = {code_by_key[k]: q for k, q in _clean_items(items, code_by_key, 'key').items() if q > 0}
    if not cleaned:
        raise QuoteError('Elige al menos una pieza.')
    name, phone = fetch_client_contact(parlor.client_code)
    if not name:
        raise QuoteError('No se encontró el cliente en Contpaqi.')
    with transaction.atomic():
        req = QuoteRequest.objects.create(
            name=name[:120], phone=phone, company=parlor.label, owner=user, from_staff=True,
            note=f'Servicio programado ({parlor.client_code}).',
        )
        QuoteRequestItem.objects.bulk_create(QuoteRequestItem(request=req, producto_codigo=c, quantity=q)
                                             for c, q in cleaned.items())
        _log(req, user, 'creó la solicitud desde Servicios')
        # Quoting a client is reaching out to them (a prospect's "contacted" mark).
        Parlor.objects.filter(pk=parlor.pk).update(contacted_at=timezone.now(), contacted_by=user)
        due = {}
        for i in items:
            day = parse_date(str(i.get('due') or ''))  # sent by the agenda, from the part's row
            if i.get('code') and day:
                due[str(i['code'])] = min(due.get(str(i['code']), day.isoformat()), day.isoformat())
        ServiceQuote.objects.create(parlor=parlor, request=req, due=due, places=[
            [str(i.get('code', '')), str(i.get('group', ''))] for i in items if i.get('code')])
    return req

"""Client directory -> Notion: copies the active ERP clients (id, code, name, phones, email, zone,
town, Maps link) into a Notion database, so the service calendar can pick a client through a
Relation and show their details through Rollups.

One way only: the ERP is read-only (SELECTs only here) and every synced property is overwritten
on each run, so corrections belong in Contpaqi. Clients that stop being active get Activo
unticked, never deleted, so calendar entries keep their link. The database id and token come
from settings (backend/.env), since the repo is public."""

import re
import time
from datetime import date, timedelta

from django.conf import settings
from django.db import connections

from commissions.services import FACTURA_DOC_TYPE
from fleet.services import notion, notion_query
from profitability.models import SavedPlace

ACTIVE_DAYS = 365           # invoiced within this window = active
NEW_CLIENT_DAYS = 91        # or registered in the ERP within this window (first service before any sale)
WALK_IN_CLIENT = 210        # 'Ventas público en general': walk-in sales, not a real client
COMPANY_EMAILS = ('agrostma', 'ventasgeasm')   # the company's own addresses, copied on invoices
TWO_DIGIT_AREA_CODES = ('33', '55', '81')      # Guadalajara, CDMX, Monterrey; the rest use 3 digits
NOTION_WRITE_PAUSE = 0.35   # Notion allows about 3 requests per second

# Notion property name -> type. The database must have exactly these (check_schema).
PROPERTIES = {
    'Nombre': 'title',
    'ID ERP': 'number',
    'Código': 'rich_text',
    'Teléfono': 'phone_number',
    'Teléfono 2': 'phone_number',
    'Email': 'email',
    'Zona': 'select',
    'Municipio': 'rich_text',
    'Ubicación': 'url',
    'Activo': 'checkbox',
}


# --- ERP and local data -------------------------------------------------------------------

def fetch_active_clients(today):
    """Clients invoiced in the last year or registered in the last three months, with their
    assigned agent and their fiscal address (CTIPODIRECCION 0, one per client, holds the phones)."""
    with connections['erp'].cursor() as cursor:
        cursor.execute('''
            SELECT c.CIDCLIENTEPROVEEDOR, c.CCODIGOCLIENTE, c.CRAZONSOCIAL, c.CEMAIL1, a.CNOMBREAGENTE,
                   d.CTELEFONO1, d.CTELEFONO2, d.CMUNICIPIO
            FROM admClientes c
            LEFT JOIN admAgentes a ON a.CIDAGENTE = c.CIDAGENTEVENTA AND a.CIDAGENTE <> 0
            LEFT JOIN admDomicilios d ON d.CTIPOCATALOGO = 1 AND d.CTIPODIRECCION = 0
                 AND d.CIDCATALOGO = c.CIDCLIENTEPROVEEDOR
            WHERE c.CTIPOCLIENTE IN (1, 2) AND c.CIDCLIENTEPROVEEDOR <> %s
              AND (c.CFECHAALTA >= %s OR EXISTS (
                  SELECT 1 FROM admDocumentos doc
                  WHERE doc.CIDCLIENTEPROVEEDOR = c.CIDCLIENTEPROVEEDOR AND doc.CIDDOCUMENTODE = %s
                    AND doc.CCANCELADO = 0 AND doc.CFECHA >= %s))
        ''', [WALK_IN_CLIENT, today - timedelta(days=NEW_CLIENT_DAYS), FACTURA_DOC_TYPE,
              today - timedelta(days=ACTIVE_DAYS)])
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def exact_locations():
    """client id -> Google Maps link of their first exact saved place. Town-level (approximate)
    places are left out: they say no more than Municipio and could send a technician astray."""
    links = {}
    for place in SavedPlace.objects.filter(approximate=False, lat__isnull=False).order_by('id'):
        for client_id in place.client_ids:
            links.setdefault(client_id, f'https://www.google.com/maps?q={place.lat},{place.lng}')
    return links


# --- Pure functions -----------------------------------------------------------------------

def format_phone(raw):
    """'(378) 712 34 56' -> '378 712 3456', '33-1388-3418' -> '33 1388 3418'. Anything that isn't
    10 digits (or 12 with a 52 country code) comes back trimmed but otherwise as typed."""
    raw = (raw or '').strip()
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 12 and digits.startswith('52'):
        digits = digits[2:]
    if len(digits) != 10:
        return raw or None
    area = 2 if digits[:2] in TWO_DIGIT_AREA_CODES else 3
    return f'{digits[:area]} {digits[area:6]} {digits[6:]}'


def client_email(raw):
    """First address in CEMAIL1 that isn't one of the company's own."""
    for email in re.split(r'[;,\s]+', raw or ''):
        if '@' in email and not any(mark in email.lower() for mark in COMPANY_EMAILS):
            return email
    return None


def client_values(row, maps_link):
    """One ERP row -> plain values keyed by Notion property name (None = empty)."""
    phone, phone2 = format_phone(row['CTELEFONO1']), format_phone(row['CTELEFONO2'])
    return {
        'Nombre': (row['CRAZONSOCIAL'] or '').strip() or None,
        'ID ERP': row['CIDCLIENTEPROVEEDOR'],
        'Código': (row['CCODIGOCLIENTE'] or '').strip() or None,
        'Teléfono': phone or phone2,
        'Teléfono 2': phone2 if phone and phone2 != phone else None,
        'Email': client_email(row['CEMAIL1']),
        'Zona': (row['CNOMBREAGENTE'] or '').strip() or None,
        'Municipio': (row['CMUNICIPIO'] or '').strip() or None,
        'Ubicación': maps_link,
        'Activo': True,
    }


def to_notion(values):
    def prop(kind, value):
        if kind in ('title', 'rich_text'):
            return {kind: [{'text': {'content': value}}] if value else []}
        if kind == 'select':
            return {'select': {'name': value} if value else None}
        return {kind: value}
    return {name: prop(PROPERTIES[name], value) for name, value in values.items()}


def from_notion(page):
    """A Notion page -> the same plain values client_values builds."""
    def value(prop):
        raw = prop[prop['type']]
        if prop['type'] in ('title', 'rich_text'):
            return ''.join(t['plain_text'] for t in raw) or None
        if prop['type'] == 'select':
            return raw['name'] if raw else None
        return raw
    return {name: value(page['properties'][name]) for name in PROPERTIES}


def plan_changes(wanted, existing):
    """wanted: client id -> values; existing: client id -> (page id, values).
    Returns (values to create, [(page id, changed values)]). Pages of clients no longer active
    only get Activo unticked; their other properties are left as last synced."""
    creates = [values for client_id, values in wanted.items() if client_id not in existing]
    updates = []
    for client_id, (page_id, current) in existing.items():
        values = wanted.get(client_id, {'Activo': False})
        changed = {name: value for name, value in values.items() if current.get(name) != value}
        if changed:
            updates.append((page_id, changed))
    return creates, updates


def schema_problems(database):
    found = {name: prop['type'] for name, prop in database['properties'].items()}
    return [f'"{name}" ({kind})' for name, kind in PROPERTIES.items() if found.get(name) != kind]


# --- Sync ---------------------------------------------------------------------------------

def sync_clients(log, dry_run=False, today=None):
    database_id = settings.NOTION_CLIENTS_DB
    problems = schema_problems(notion('GET', f'databases/{database_id}'))
    if problems:
        raise ValueError('The Notion clients database is missing or has the wrong type for: ' + ', '.join(problems))

    links = exact_locations()
    rows = fetch_active_clients(today or date.today())
    wanted = {row['CIDCLIENTEPROVEEDOR']: client_values(row, links.get(row['CIDCLIENTEPROVEEDOR'])) for row in rows}
    existing = {}
    for page in notion_query(database_id, {'property': 'ID ERP', 'number': {'is_not_empty': True}}):
        values = from_notion(page)
        existing[values['ID ERP']] = (page['id'], values)

    creates, updates = plan_changes(wanted, existing)
    deactivated = sum(1 for _, changed in updates if changed.get('Activo') is False)
    log(f'{len(wanted)} active clients in the ERP, {len(existing)} pages in Notion: '
        f'{len(creates)} to create, {len(updates) - deactivated} to update, {deactivated} to mark inactive.')
    if dry_run:
        return

    for values in creates:
        notion('POST', 'pages', {'parent': {'database_id': database_id}, 'properties': to_notion(values)})
        time.sleep(NOTION_WRITE_PAUSE)
    for page_id, changed in updates:
        notion('PATCH', f'pages/{page_id}', {'properties': to_notion(changed)})
        time.sleep(NOTION_WRITE_PAUSE)
    log('Done.')

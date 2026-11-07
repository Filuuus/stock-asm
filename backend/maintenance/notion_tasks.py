"""Approved Servicios quotes -> the crew's Notion calendar (Tareas), so Liz gives each visit a date there.

A task is created the moment the client approves the quote from their link (in the background: the client's
click never waits on Notion), and the nightly sync_parlors retries any that didn't make it. The task links the
client's page in the Notion Clientes database (by Código), so its phone and place show through the rollups.
Reopening or closing the quote by hand takes the task back if nobody scheduled it yet; otherwise it's left to
Liz with a note. A sale changes nothing: the crew marks the task done.

The database id and token come from settings (backend/.env), since the repo is public.
"""
import logging
import threading
from datetime import date

from django.conf import settings
from django.db import close_old_connections

from fleet.services import notion, notion_query

log = logging.getLogger(__name__)

NOT_STARTED = 'Sin empezar'
# The page icon, by the task's first category (services.CATEGORIES); 🔧 for any other.
ICONS = {
    'Colectores': '🐄', 'Pulsadores': '⏱️', 'Vaso pesador': '⚖️', 'Banco de válvulas': '🔩', 'Retiradores': '🦾',
    'Recibidor de leche': '🥛', 'Bomba de leche': '🫗', 'Trampa de líquidos': '💧', 'Regulador de vacío': '🎚️',
    'Sistema de vacío': '💨', 'Lavado': '🧼', 'Enfriamiento': '❄️', 'Arreador': '🚧', 'Pediluvio': '🦶',
}
MAX_TEXT = 2000  # Notion's limit for one rich-text piece
MONTHS = ('ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic')


def enabled():
    return bool(settings.NOTION_TOKEN and settings.NOTION_SERVICE_TASKS_DB)


def day_label(iso):
    d = date.fromisoformat(iso) if isinstance(iso, str) else iso
    return f'{d.day} {MONTHS[d.month - 1]} {d.year}'


def joined(words):
    """['a', 'b', 'c'] -> 'a, b y c'."""
    return words[0] if len(words) == 1 else f'{", ".join(words[:-1])} y {words[-1]}'


def task_values(*, number, client, categories, items, total, owner, accepted_on, link, stalls=None):
    """The task's content as plain values, laid out like the calendar's own template (Tipo de sala, Marca del
    equipo, a Materiales table, Información adicional). items: [(quantity, code, name, due iso or None)];
    categories: the parlor groups the quote covers. Prioritaria when a part was already overdue the day the client
    approved."""
    today = accepted_on.isoformat()
    overdue = any(due and due < today for *_, due in items)
    jobs = joined([c.lower() for c in categories]) if categories else ''
    return {
        'Actividad': f'Cambio de {jobs} {client.title()}' if jobs else f'Servicio {client.title()}',
        'Estado': NOT_STARTED,
        'Prioridad': 'Prioritaria' if overdue else 'Regular',
        'Solicita': owner or '',
        'Descripción': f'Cambio de {jobs} (cotización #{number})' if jobs else f'Cotización #{number}',
        'icon': ICONS.get(categories[0], '🔧') if categories else '🔧',  # the first one, as the title lists them
        'sala': f'{stalls} unidades' if stalls else '',
        'materiales': [(f'{qty:g}', code, name, f'{"Vencía" if due < today else "Toca"} {day_label(due)}' if due else '')
                       for qty, code, name, due in items],
        # Lines of (text, link or None) pieces: the quote's link is a clickable "ver cotización".
        'info': [[(f'Cotización #{number} (', None), ('ver cotización', link),
                  (f'), aprobada por el cliente el {day_label(accepted_on)}', None)],
                 [(f'Total: ${total:,.2f} IVA incluido', None)]],
    }


def _text(s, link=None):
    return [{'text': {'content': s[:MAX_TEXT], **({'link': {'url': link}} if link else {})}}] if s else []


def to_properties(values, client_page=None):
    props = {
        'Actividad': {'title': _text(values['Actividad'])},
        'Estado': {'status': {'name': values['Estado']}},
        'Prioridad': {'multi_select': [{'name': values['Prioridad']}]},
        'Solicita': {'rich_text': _text(values['Solicita'])},
        'Descripción': {'rich_text': _text(values['Descripción'])},
    }
    if client_page:
        props['Nombre del cliente'] = {'relation': [{'id': client_page}]}
    return props


def paragraph(s):
    """s: plain text, or [(text, link or None), ...] pieces."""
    pieces = [_text(t, url) for t, url in s] if isinstance(s, list) else [_text(s)]
    return {'type': 'paragraph', 'paragraph': {'rich_text': [r for p in pieces for r in p]}}


def to_children(values):
    """The page body, as the calendar's template has it; one blank Materiales row for the crew's additions."""
    rows = [('Cantidad', 'No. Referencia', 'Descripción', 'Observaciones'), *values['materiales'], ('', '', '', '')]
    return [
        paragraph(f'Tipo de sala: {values["sala"]}'.rstrip()),
        paragraph('Marca del equipo:'),
        {'type': 'heading_1', 'heading_1': {'rich_text': _text('Materiales')}},
        {'type': 'table', 'table': {'table_width': 4, 'has_column_header': True, 'has_row_header': False, 'children': [
            {'type': 'table_row', 'table_row': {'cells': [_text(c) for c in row]}} for row in rows]}},
        {'type': 'heading_1', 'heading_1': {'rich_text': _text('Información adicional')}},
        *[paragraph(line) for line in values['info']],
    ]


def quote_values(service):
    """task_values for a ServiceQuote, from its request's frozen prices."""
    from api.services import _catalog
    from catalog.quotes import _display, _rows, _totals

    req = service.request
    rows = _rows(req, {p['CCODIGOPRODUCTO']: p for p in _catalog(True)}, live_prices=False)
    categories = list(dict.fromkeys(group for _, group in service.places if group))
    return task_values(
        number=req.pk, client=req.name, categories=categories,
        items=[(float(r['quantity']), r['code'], r['name'], r['due']) for r in rows], stalls=service.parlor.stalls,
        total=float(_totals(req, rows)['total']), owner=_display(req.owner),
        accepted_on=req.accepted_at.date(),
        link=f'{settings.PUBLIC_SITE_URL}/solicitud/{req.token}',  # the client's page: opens outside the office
    )


def client_page(code):
    pages = notion_query(settings.NOTION_CLIENTS_DB, {'property': 'Código', 'rich_text': {'equals': code}})
    return pages[0]['id'] if pages else None


def create_task(service):
    """Creates the quote's task if it has none; returns whether it did."""
    if service.notion_page or not service.request.accepted_at:
        return False
    values = quote_values(service)
    page = notion('POST', 'pages', {
        'parent': {'database_id': settings.NOTION_SERVICE_TASKS_DB},
        'icon': {'type': 'emoji', 'emoji': values['icon']},
        'properties': to_properties(values, client_page(service.parlor.client_code)),
        'children': to_children(values),
    })
    service.notion_page = page['id']
    service.save(update_fields=['notion_page'])
    return True


def withdraw_task(service, why):
    """The quote was reopened or closed by hand: its task goes to Notion's trash if it's still unscheduled, else
    its page gets a note. Either way the quote forgets it, so approving again makes a new one."""
    if not service.notion_page:
        return
    page = notion('GET', f'pages/{service.notion_page}')
    props = page['properties']
    if props['Estado']['status'] and props['Estado']['status']['name'] == NOT_STARTED and not props['Fecha']['date']:
        notion('PATCH', f'pages/{service.notion_page}', {'archived': True})
    else:  # a line at the end of its page, under Información adicional
        note = f'⚠ La cotización #{service.request_id} {why} el {day_label(date.today())}.'
        notion('PATCH', f'blocks/{service.notion_page}/children', {'children': [paragraph(note)]})
    service.notion_page = ''
    service.save(update_fields=['notion_page'])


def in_background(fn, request_id, *args):
    """Runs fn(service quote, *args) after the response, for a Servicios request; failures are logged (the
    nightly sync retries creations)."""
    if not enabled():
        return

    def run():
        from .models import ServiceQuote
        try:
            service = ServiceQuote.objects.select_related('request__owner', 'parlor').filter(request_id=request_id).first()
            if service:
                fn(service, *args)
        except Exception:
            log.exception('Notion task for request %s failed', request_id)
        finally:
            close_old_connections()

    threading.Thread(target=run, daemon=True).start()


def sync_tasks(out=print):
    """The nightly retry: a task for every approved, still shared Servicios quote that has none."""
    from .models import ServiceQuote

    if not enabled():
        return
    pending = ServiceQuote.objects.select_related('request__owner', 'parlor').filter(
        request__status='APPROVED', request__accepted_at__isnull=False, notion_page='')
    made = sum(create_task(s) for s in pending)
    out(f'{made} Notion tasks created for approved service quotes')

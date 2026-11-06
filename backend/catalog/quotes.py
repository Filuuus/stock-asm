"""Quote requests: the public cart sent for pricing (see QuoteRequest).

Prices only ever leave the server for an approved request, and then only the
prices frozen at approval - never the live catalog price.
"""
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from api.services import _catalog, scrub

from .models import QuoteEvent, QuoteRequest, QuoteRequestItem

MAX_ITEMS = 100
DEFAULT_VALID_DAYS = 15
MAX_PRICE = Decimal('100000000')
MAX_NOTE = 2000
# Business days a request can wait before it stands out: a new one with nobody contacting it,
# a contacted one with no activity at all (nothing here can see WhatsApp).
NEW_AMBER_DAYS, NEW_RED_DAYS, STALE_DAYS = 1, 2, 3
OPEN_STATUSES = (QuoteRequest.STATUS_NEW, QuoteRequest.STATUS_CONTACTED)
AREA_RE = re.compile(r'Área: ([^,]+)')


class QuoteError(ValueError):
    """A request that can't be accepted; the message is shown to the user."""


def _clean_items(items, by_code, field='code'):
    if not isinstance(items, list) or not items:
        raise QuoteError('La solicitud no tiene productos.')
    if len(items) > MAX_ITEMS:
        raise QuoteError(f'Máximo {MAX_ITEMS} productos por solicitud.')
    cleaned = {}
    for item in items:
        code = str((item or {}).get(field, '')).strip()
        if code not in by_code:
            raise QuoteError(f'Producto no encontrado: {code or "(vacío)"}.')
        try:
            qty = Decimal(str(item.get('quantity'))).quantize(Decimal('0.01'))
        except (InvalidOperation, TypeError):
            raise QuoteError(f'Cantidad no válida para {code}.')
        if qty < 0 or qty > 100000:
            raise QuoteError(f'Cantidad no válida para {code}.')
        cleaned[code] = cleaned.get(code, Decimal(0)) + qty
    return cleaned


def _clean_price(value, code):
    """A price staff typed, IVA included; blank clears it, back to the catalog's."""
    if value in (None, ''):
        return None
    try:
        price = Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError):
        raise QuoteError(f'Precio no válido para {code}.')
    if not 0 < price <= MAX_PRICE:
        raise QuoteError(f'Precio no válido para {code}.')
    return price


def _can_modify(req):
    return req.status != QuoteRequest.STATUS_REJECTED


def _contacted(req):
    """The office number is only for customers someone has already talked to; a change to
    a request counts as the same conversation."""
    return bool(
        req.status == QuoteRequest.STATUS_APPROVED or req.contacted_at or req.sent_at
        or (req.revises and _contacted(req.revises))
    )


def create_request(data):
    # A change from the customer's link: who it is comes from the original, so the
    # link's page never has to show their phone.
    original = None
    if data.get('revises'):
        original = QuoteRequest.objects.filter(token=str(data['revises'])).first()
        if not original or not _can_modify(original):
            raise QuoteError('Esa solicitud ya no se puede modificar.')
    name = original.name if original else str(data.get('name', '')).strip()
    phone = original.phone if original else str(data.get('phone', '')).strip()
    if not name or not phone:
        raise QuoteError('Nombre y teléfono son obligatorios.')
    if len(name) > 120 or len(phone) > 30 or sum(c.isdigit() for c in phone) < 10:
        raise QuoteError('Revisa el nombre y el teléfono (10 dígitos).')
    # The cart sends the public product key; requests store the ERP code.
    code_by_key = {p['key']: p['CCODIGOPRODUCTO'] for p in _catalog(True)}
    items = {code_by_key[k]: q for k, q in _clean_items(data.get('items'), code_by_key, 'key').items() if q > 0}
    if not items:
        raise QuoteError('La solicitud no tiene productos.')
    with transaction.atomic():
        req = QuoteRequest.objects.create(
            name=name, phone=phone,
            company=original.company if original else str(data.get('company', '')).strip()[:120],
            note=str(data.get('note', '')).strip()[:2000],
            revises=original, owner=original.owner if original else None,
        )
        QuoteRequestItem.objects.bulk_create(
            QuoteRequestItem(request=req, producto_codigo=c, quantity=q) for c, q in items.items()
        )
        if original:
            _log(original, None, f'envió cambios desde el enlace del cliente: solicitud #{req.pk}')
    return req


def business_days_since(start, now):
    """Whole weekdays from start's date to now's; a weekend adds nothing."""
    day, end, days = timezone.localtime(start).date(), timezone.localtime(now).date(), 0
    while day < end:
        day += timedelta(days=1)
        days += day.weekday() < 5
    return days


def _display(user):
    return (user.get_full_name() or user.username) if user else None


def _log(req, user, text, kind=QuoteEvent.ACTION):
    QuoteEvent.objects.create(request=req, author=user, text=text, kind=kind)


def _last_activity(req):
    return getattr(req, 'last_event', None) or req.contacted_at or req.created_at


def _attention(req, now):
    """amber or red when a request has waited too long, None otherwise."""
    if req.status == QuoteRequest.STATUS_NEW:
        days = business_days_since(req.created_at, now)
        return 'red' if days >= NEW_RED_DAYS else 'amber' if days >= NEW_AMBER_DAYS else None
    if req.status == QuoteRequest.STATUS_CONTACTED:
        return 'stale' if business_days_since(_last_activity(req), now) >= STALE_DAYS else None
    return None


def _to_send(req):
    return req.status == QuoteRequest.STATUS_APPROVED and req.sent_at is None


def _with_activity(requests):
    return requests.annotate(last_event=Max('events__created_at'))


def pending_count():
    """The menu badge: what needs someone and has nobody moving it."""
    now = timezone.now()
    return sum(
        1 for r in _with_activity(QuoteRequest.objects.exclude(status=QuoteRequest.STATUS_REJECTED))
        if (r.status == QuoteRequest.STATUS_NEW and r.owner_id is None) or _to_send(r)
        or _attention(r, now) == 'stale'
    )


def _image(product):
    images = product.get('images') or []
    img = next((i for i in images if i['is_primary']), images[0] if images else None)
    return img['file'] if img else None


def _rows(req, by_code, live_prices):
    """One row per item. live_prices: the staff view (current catalog price and
    stock). Otherwise only the price frozen at approval, if any."""
    rows = []
    for item in req.items.all():
        p = by_code.get(item.producto_codigo, {})
        if live_prices:
            price = item.unit_price or p.get('price') or None
        else:
            price = item.unit_price if req.status == QuoteRequest.STATUS_APPROVED else None
        price = Decimal(str(price)) if price else None
        rows.append({
            'key': p.get('key'),  # links to the product page
            'code': item.producto_codigo,
            'name': p.get('CNOMBREPRODUCTO', item.producto_codigo),
            'image': _image(p),
            'quantity': item.quantity,
            'unit_price': price,
            **({'typed_price': item.unit_price, 'catalog_price': p.get('price') or None} if live_prices else {}),
            'subtotal': (price * item.quantity).quantize(Decimal('0.01')) if price else None,
            **({'stock': p.get('stock'), 'in_stock': p.get('in_stock')} if live_prices else {}),
        })
    return rows


def _totals(req, rows):
    """{'subtotal', 'discount' (percent), 'discount_amount', 'total'}: the request's discount on its priced rows."""
    subtotal = _total(rows)
    off = (subtotal * req.discount / 100).quantize(Decimal('0.01'))
    return {'subtotal': subtotal, 'discount': req.discount, 'discount_amount': off, 'total': subtotal - off}


def _total(rows):
    return sum((r['subtotal'] for r in rows if r['subtotal']), Decimal(0))


def _expired(req):
    return req.status == QuoteRequest.STATUS_APPROVED and bool(req.valid_until) and req.valid_until < timezone.localdate()


def public_view(req):
    """What the customer sees at /solicitud/<token>: no live prices, no codes."""
    # Every product, not just what's in stock now, so names still resolve.
    by_code = {p['CCODIGOPRODUCTO']: p for p in _catalog(True)}
    # A hidden or out-of-stock product has no public page to link to; the key still goes in the cart.
    public_keys = {p['key'] for p in _catalog(False)}
    rows = [{**r, 'linked': r['key'] in public_keys} for r in scrub(_rows(req, by_code, live_prices=False))]
    approved = req.status == QuoteRequest.STATUS_APPROVED
    revision = req.revisions.exclude(status=QuoteRequest.STATUS_REJECTED).order_by('-pk').first()
    return {
        # Contacted is internal: the customer's request is still in review.
        'number': req.pk, 'status': QuoteRequest.STATUS_NEW if req.status == QuoteRequest.STATUS_CONTACTED else req.status,
        'created_at': req.created_at, 'name': req.name, 'valid_until': req.valid_until if approved else None,
        'items': rows, **(_totals(req, rows) if approved else {'total': None, 'discount': req.discount}),
        'expired': _expired(req), 'can_modify': _can_modify(req),
        'contact_phone': settings.QUOTE_CONTACT_PHONE if _contacted(req) else None,
        'revision': {'number': revision.pk, 'token': revision.token} if revision else None,
        'revises': {'number': req.revises.pk, 'token': req.revises.token} if req.revises else None,
    }


def staff_list():
    by_code = {p['CCODIGOPRODUCTO']: p for p in _catalog(True)}
    now = timezone.now()
    rows = []
    # order_by is needed: a query with Max() drops the model's default ordering.
    newest = _with_activity(QuoteRequest.objects.select_related('owner').prefetch_related('items')).order_by('-created_at', '-pk')
    for r in newest[:200]:
        area = AREA_RE.search(r.note)
        rows.append({
            'id': r.pk, 'status': r.status, 'created_at': r.created_at, 'name': r.name, 'company': r.company,
            'phone': r.phone, 'owner': _display(r.owner), 'attention': _attention(r, now), 'to_send': _to_send(r),
            'expired': _expired(r),
            'comparison': r.note.startswith('Comparando opciones'), 'area': area[1] if area else None,
            'items': [by_code.get(i.producto_codigo, {}).get('CNOMBREPRODUCTO', i.producto_codigo) for i in r.items.all()],
        })
    return rows


def staff_view(req, user):
    by_code = {p['CCODIGOPRODUCTO']: p for p in _catalog(True)}
    # Approved requests show the frozen prices; open ones the live prices.
    rows = _rows(req, by_code, live_prices=req.status in OPEN_STATUSES)
    if req.status not in OPEN_STATUSES:
        for r in rows:
            r.update(stock=by_code.get(r['code'], {}).get('stock'))
    return {
        'id': req.pk, 'token': req.token, 'status': req.status, 'created_at': req.created_at,
        'name': req.name, 'phone': req.phone, 'company': req.company, 'note': req.note,
        'decided_at': req.decided_at, 'decided_by': req.decided_by.username if req.decided_by else None,
        'valid_until': req.valid_until, 'items': rows, **_totals(req, rows),
        'owner': _display(req.owner), 'mine': req.owner_id == user.pk, 'to_send': _to_send(req),
        'expired': _expired(req), 'revises': req.revises_id,
        'revisions': list(req.revisions.values_list('pk', flat=True)),
        'events': [{
            'id': e.pk, 'kind': e.kind, 'text': e.text, 'author': _display(e.author), 'created_at': e.created_at,
            'mine': e.author_id == user.pk,
        } for e in req.events.select_related('author')],
    }


def _require_open(req):
    if req.status not in OPEN_STATUSES:
        raise QuoteError('Esta solicitud ya fue atendida.')


def mark_contacted(req, user):
    """From the WhatsApp link or the manual button; whoever writes first takes an unowned request."""
    if req.status != QuoteRequest.STATUS_NEW:
        return
    req.status, req.contacted_at = QuoteRequest.STATUS_CONTACTED, timezone.now()
    req.owner = req.owner or user
    req.save()
    _log(req, user, 'marcó la solicitud como contactada')


def undo_contacted(req, user):
    if req.status != QuoteRequest.STATUS_CONTACTED:
        raise QuoteError('Esta solicitud no está contactada.')
    req.status, req.contacted_at = QuoteRequest.STATUS_NEW, None
    if req.owner_id == user.pk:
        req.owner = None
    req.save()
    _log(req, user, 'deshizo el contacto')


def take(req, user):
    if req.owner_id != user.pk:
        req.owner = user
        req.save()
        _log(req, user, 'tomó la solicitud')


def release(req, user):
    if req.owner_id is not None:
        req.owner = None
        req.save()
        _log(req, user, 'soltó la solicitud')


def mark_sent(req, user):
    if not _to_send(req):
        return
    req.sent_at = timezone.now()
    req.save()
    _log(req, user, 'envió la cotización')


def set_discount(req, user, value):
    """A discount on the whole request, in percent (El Buen Fin, a deal to win a client back): set while it's
    open, so management approves it with the prices."""
    _require_open(req)
    try:
        discount = Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError):
        raise QuoteError('Descuento no válido.')
    if not 0 <= discount < 100:
        raise QuoteError('El descuento va de 0 a 99 %.')
    if discount != req.discount:
        req.discount = discount
        req.save(update_fields=['discount'])
        _log(req, user, f'puso un descuento de {discount.normalize():f} %' if discount else 'quitó el descuento')


def set_phone(req, user, phone):
    """Staff fix the customer's phone (a request made from Servicios takes Contpaqi's, which can be missing or a
    landline), so WhatsApp reaches them."""
    phone = str(phone or '').strip()
    if len(phone) > 30 or sum(c.isdigit() for c in phone) < 10:
        raise QuoteError('Revisa el teléfono (10 dígitos).')
    if phone != req.phone:
        req.phone = phone
        req.save(update_fields=['phone'])
        _log(req, user, f'cambió el teléfono a {phone}')


def add_note(req, user, text):
    text = str(text or '').strip()
    if not text:
        raise QuoteError('Escribe la nota.')
    if len(text) > MAX_NOTE:
        raise QuoteError(f'Máximo {MAX_NOTE} caracteres.')
    _log(req, user, text, QuoteEvent.NOTE)


def delete_note(req, user, pk):
    if not req.events.filter(pk=pk, kind=QuoteEvent.NOTE, author=user).delete()[0]:
        raise QuoteError('Solo puedes borrar tus propias notas.')


def set_items(req, items, user=None):
    """Staff adjust the products, quantities and prices before approving; quantity 0 removes
    an item, a code not on the request adds it. A typed price overrides the catalog's and is
    kept when management approves."""
    _require_open(req)
    known = {i.producto_codigo for i in req.items.all()} | {p['CCODIGOPRODUCTO'] for p in _catalog(True)}
    cleaned = _clean_items(items, known)
    prices = {str(i['code']).strip(): _clean_price(i['unit_price'], i['code']) for i in items if 'unit_price' in i}
    with transaction.atomic():
        for code, qty in cleaned.items():
            if qty == 0:
                req.items.filter(producto_codigo=code).delete()
            else:
                typed = {'unit_price': prices[code]} if code in prices else {}
                req.items.update_or_create(producto_codigo=code, defaults={'quantity': qty, **typed})
        if not req.items.exists():  # inside the transaction: nothing is removed
            raise QuoteError('La solicitud debe conservar al menos un producto.')
    _log(req, user, 'actualizó productos y precios')


def approve(req, user, valid_days=DEFAULT_VALID_DAYS):
    _require_open(req)
    try:
        valid_days = int(valid_days)
    except (TypeError, ValueError):
        raise QuoteError('Vigencia no válida.')
    if not 1 <= valid_days <= 365:
        raise QuoteError('La vigencia debe ser de 1 a 365 días.')
    # IVA included, like the catalog shows it.
    prices = {p['CCODIGOPRODUCTO']: p['price'] for p in _catalog(True)}
    with transaction.atomic():
        for item in req.items.all():
            if item.unit_price is not None:  # typed by staff
                continue
            price = prices.get(item.producto_codigo)
            # $0 / missing price: left empty, the customer sees "se cotiza aparte".
            item.unit_price = Decimal(str(price)).quantize(Decimal('0.01')) if price else None
            item.save(update_fields=['unit_price'])
        req.status = QuoteRequest.STATUS_APPROVED
        req.decided_at = timezone.now()
        req.decided_by = user
        req.valid_until = timezone.localdate() + timedelta(days=valid_days)
        req.save()
        _log(req, user, 'aprobó la cotización')


def reopen(req, user):
    """Gerencia fixes an approved quote: back to contacted, prices off the customer's link until approved again."""
    if req.status != QuoteRequest.STATUS_APPROVED:
        raise QuoteError('Solo se puede reabrir una cotización aprobada.')
    prices = {p['CCODIGOPRODUCTO']: p['price'] for p in _catalog(True)}
    with transaction.atomic():
        for item in req.items.all():
            live = prices.get(item.producto_codigo)
            if live and item.unit_price == Decimal(str(live)).quantize(Decimal('0.01')):  # frozen, not typed
                item.unit_price = None
                item.save(update_fields=['unit_price'])
        req.status, req.valid_until, req.sent_at = QuoteRequest.STATUS_CONTACTED, None, None
        req.decided_at, req.decided_by = None, None
        req.contacted_at = req.contacted_at or timezone.now()
        req.save()
        _log(req, user, 'reabrió la cotización')


def close(req, user, reason):
    """Any staff member, at any point: the reason stays in the timeline, never on the customer's link."""
    reason = str(reason or '').strip()
    if not reason:
        raise QuoteError('Escribe por qué se cierra.')
    if len(reason) > MAX_NOTE:
        raise QuoteError(f'Máximo {MAX_NOTE} caracteres.')
    if req.status == QuoteRequest.STATUS_REJECTED:
        raise QuoteError('Esta solicitud ya está cerrada.')
    with transaction.atomic():
        req.status = QuoteRequest.STATUS_REJECTED
        req.decided_at = timezone.now()
        req.decided_by = user
        req.save()
        _log(req, user, f'cerró la solicitud: {reason}')

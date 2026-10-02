"""Quote requests: the public cart sent for pricing (see QuoteRequest).

Prices only ever leave the server for an approved request, and then only the
prices frozen at approval - never the live catalog price.
"""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from api.services import get_inventory_catalog

from .models import QuoteRequest, QuoteRequestItem

MAX_ITEMS = 100
DEFAULT_VALID_DAYS = 15


class QuoteError(ValueError):
    """A request that can't be accepted; the message is shown to the user."""


def _clean_items(items, by_code):
    if not isinstance(items, list) or not items:
        raise QuoteError('La solicitud no tiene productos.')
    if len(items) > MAX_ITEMS:
        raise QuoteError(f'Máximo {MAX_ITEMS} productos por solicitud.')
    cleaned = {}
    for item in items:
        code = str((item or {}).get('code', '')).strip()
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


def create_request(data):
    name = str(data.get('name', '')).strip()
    phone = str(data.get('phone', '')).strip()
    if not name or not phone:
        raise QuoteError('Nombre y teléfono son obligatorios.')
    if len(name) > 120 or len(phone) > 30 or sum(c.isdigit() for c in phone) < 10:
        raise QuoteError('Revisa el nombre y el teléfono (10 dígitos).')
    by_code = {p['CCODIGOPRODUCTO'] for p in get_inventory_catalog(False)}
    items = {c: q for c, q in _clean_items(data.get('items'), by_code).items() if q > 0}
    if not items:
        raise QuoteError('La solicitud no tiene productos.')
    with transaction.atomic():
        req = QuoteRequest.objects.create(
            name=name, phone=phone,
            company=str(data.get('company', '')).strip()[:120],
            note=str(data.get('note', '')).strip()[:2000],
        )
        QuoteRequestItem.objects.bulk_create(
            QuoteRequestItem(request=req, producto_codigo=c, quantity=q) for c, q in items.items()
        )
    return req


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
            price = p.get('CPRECIO1') or None
        else:
            price = item.unit_price if req.status == QuoteRequest.STATUS_APPROVED else None
        price = Decimal(str(price)) if price else None
        rows.append({
            'code': item.producto_codigo,
            'name': p.get('CNOMBREPRODUCTO', item.producto_codigo),
            'image': _image(p),
            'quantity': item.quantity,
            'unit_price': price,
            'subtotal': (price * item.quantity).quantize(Decimal('0.01')) if price else None,
            **({'stock': p.get('stock'), 'in_stock': p.get('in_stock')} if live_prices else {}),
        })
    return rows


def _total(rows):
    return sum((r['subtotal'] for r in rows if r['subtotal']), Decimal(0))


def public_view(req):
    """What the customer sees at /solicitud/<token>."""
    by_code = {p['CCODIGOPRODUCTO']: p for p in get_inventory_catalog(False)}
    rows = _rows(req, by_code, live_prices=False)
    approved = req.status == QuoteRequest.STATUS_APPROVED
    return {
        'number': req.pk, 'status': req.status, 'created_at': req.created_at,
        'name': req.name, 'valid_until': req.valid_until if approved else None,
        'items': rows, 'total': _total(rows) if approved else None,
    }


def staff_list():
    return [{
        'id': r.pk, 'status': r.status, 'created_at': r.created_at, 'name': r.name,
        'company': r.company, 'items': r.items.count(),
    } for r in QuoteRequest.objects.all()[:200]]


def staff_view(req):
    by_code = {p['CCODIGOPRODUCTO']: p for p in get_inventory_catalog(True)}
    # Approved requests show the frozen prices; open ones the live prices.
    rows = _rows(req, by_code, live_prices=req.status == QuoteRequest.STATUS_NEW)
    if req.status != QuoteRequest.STATUS_NEW:
        for r in rows:
            r.update(stock=by_code.get(r['code'], {}).get('stock'))
    return {
        'id': req.pk, 'token': req.token, 'status': req.status, 'created_at': req.created_at,
        'name': req.name, 'phone': req.phone, 'company': req.company, 'note': req.note,
        'decided_at': req.decided_at, 'decided_by': req.decided_by.username if req.decided_by else None,
        'valid_until': req.valid_until, 'items': rows, 'total': _total(rows),
    }


def _require_new(req):
    if req.status != QuoteRequest.STATUS_NEW:
        raise QuoteError('Esta solicitud ya fue atendida.')


def set_items(req, items):
    """Staff adjust quantities before approving; quantity 0 removes the item."""
    _require_new(req)
    by_code = {i.producto_codigo for i in req.items.all()}
    cleaned = _clean_items(items, by_code)
    with transaction.atomic():
        for code, qty in cleaned.items():
            if qty == 0:
                req.items.filter(producto_codigo=code).delete()
            else:
                req.items.filter(producto_codigo=code).update(quantity=qty)
    if not req.items.exists():
        raise QuoteError('La solicitud debe conservar al menos un producto.')


def approve(req, user, valid_days=DEFAULT_VALID_DAYS):
    _require_new(req)
    try:
        valid_days = int(valid_days)
    except (TypeError, ValueError):
        raise QuoteError('Vigencia no válida.')
    if not 1 <= valid_days <= 365:
        raise QuoteError('La vigencia debe ser de 1 a 365 días.')
    prices = {p['CCODIGOPRODUCTO']: p['CPRECIO1'] for p in get_inventory_catalog(True)}
    with transaction.atomic():
        for item in req.items.all():
            price = prices.get(item.producto_codigo)
            # $0 / missing price: left empty, the customer sees "se cotiza aparte".
            item.unit_price = Decimal(str(price)).quantize(Decimal('0.01')) if price else None
            item.save(update_fields=['unit_price'])
        req.status = QuoteRequest.STATUS_APPROVED
        req.decided_at = timezone.now()
        req.decided_by = user
        req.valid_until = timezone.localdate() + timedelta(days=valid_days)
        req.save()


def reject(req, user):
    _require_new(req)
    req.status = QuoteRequest.STATUS_REJECTED
    req.decided_at = timezone.now()
    req.decided_by = user
    req.save()

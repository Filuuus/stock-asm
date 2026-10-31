"""Management's catalog settings (/ajustes-catalogo): special-order products, hidden products, and
what the public sees per category and brand. api.services applies them."""
from django.core.cache import cache
from django.db import transaction

from api.services import SPECIAL_ORDER_ID_OFFSET, _catalog

from .models import BrandRule, CategoryRule, HiddenProduct, SpecialOrderProduct

# The catalog's categories, in the order the filters show them.
CATEGORIES = ['R', 'R_CHEM', 'R_NW', 'R_FAN', 'B', 'S']
MAX_NAME = 120
MAX_BRAND = 60


class RuleError(Exception):
    pass


def _clean_name(name):
    name = str(name or '').strip().upper()
    if not name:
        raise RuleError('Escribe el nombre.')
    if len(name) > MAX_NAME:
        raise RuleError(f'Máximo {MAX_NAME} caracteres.')
    return name


def overview():
    catalog = _catalog(True)
    by_id = {p['CIDPRODUCTO']: p for p in catalog}
    hidden = set(HiddenProduct.objects.values_list('product_id', flat=True))
    rows = {r.category: r for r in CategoryRule.objects.all()}
    public_names = dict(BrandRule.objects.values_list('erp_name', 'public_name'))
    specials = [p for p in catalog if p.get('special_order')]
    return {
        'specials': [{'key': p['key'], 'slug': p['slug'], 'name': p['CNOMBREPRODUCTO'], 'hidden': p['hidden'],
                      'photos': len(p['images'])} for p in specials],
        # Ones hidden by mistake or for products gone from the ERP still have to be listed to undo.
        'hidden': [{'key': str(pid), 'slug': by_id[pid]['slug'] if pid in by_id else '',
                    'name': by_id[pid]['CNOMBREPRODUCTO'] if pid in by_id else f'Producto {pid} (ya no está en el ERP)'}
                   for pid in sorted(hidden) if pid < SPECIAL_ORDER_ID_OFFSET],
        'categories': [{
            'category': c, 'show_price': r.show_price, 'on_order': r.on_order, 'hide_brand': r.hide_brand,
        } for c in CATEGORIES for r in [rows.get(c) or CategoryRule(category=c)]],
        'brands': [{'erp_name': b, 'public_name': public_names.get(b, '')}
                   for b in sorted({p['brand'] for p in catalog if p['brand']} | set(public_names))],
    }


def add_special(name):
    name = _clean_name(name)
    with transaction.atomic():
        last = SpecialOrderProduct.objects.order_by('-pk').first()
        SpecialOrderProduct.objects.create(code=f'ESPECIAL-{(last.pk if last else 0) + 1}', name=name)
    cache.delete('inventory_catalog')


def rename_special(key, name):
    updated = SpecialOrderProduct.objects.filter(pk=key - SPECIAL_ORDER_ID_OFFSET).update(name=_clean_name(name))
    if not updated:
        raise RuleError('Ese producto ya no existe.')
    cache.delete('inventory_catalog')


def set_hidden(key, hidden):
    if not isinstance(hidden, bool):
        raise RuleError('Valor inválido.')
    if hidden:
        if not any(p['CIDPRODUCTO'] == key for p in _catalog(True)):
            raise RuleError('Ese producto no existe.')
        HiddenProduct.objects.get_or_create(product_id=key)
    else:
        HiddenProduct.objects.filter(product_id=key).delete()


def set_category(category, data):
    if category not in CATEGORIES:
        raise RuleError('Categoría desconocida.')
    show_price, hide_brand, on_order = data.get('show_price'), data.get('hide_brand'), data.get('on_order')
    if not isinstance(show_price, bool) or not isinstance(hide_brand, bool) \
            or on_order not in dict(CategoryRule.ON_ORDER_CHOICES):
        raise RuleError('Valor inválido.')
    CategoryRule.objects.update_or_create(category=category, defaults={
        'show_price': show_price, 'hide_brand': hide_brand, 'on_order': on_order})


def set_brand(erp_name, public_name):
    erp_name = str(erp_name or '').strip()
    public_name = str(public_name or '').strip()
    if not erp_name:
        raise RuleError('Marca inválida.')
    if len(public_name) > MAX_BRAND:
        raise RuleError(f'Máximo {MAX_BRAND} caracteres.')
    if public_name:
        BrandRule.objects.update_or_create(erp_name=erp_name, defaults={'public_name': public_name})
    else:
        BrandRule.objects.filter(erp_name=erp_name).delete()

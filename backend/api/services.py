from django.core.cache import cache
from .models import AdmClasificacionesValores, AdmProductos
from catalog.services import get_images_by_codes, get_public_price_codes

# Values that mean "no supplier assigned" rather than a real brand.
NO_BRAND_VALUES = {'(Ninguna)', '(Ninguno)'}

class InventoryRepository:
    @staticmethod
    def fetch_inventory():
        return list(
            AdmProductos.objects.exclude(CIDPRODUCTO=0).values(
                'CIDPRODUCTO',
                'CCODIGOPRODUCTO',
                'CNOMBREPRODUCTO',
                'CPRECIO1',
                'CTEXTOEXTRA1',
                'CIDVALORCLASIFICACION1',
            )
        )

    @staticmethod
    def fetch_brand_names():
        return dict(
            AdmClasificacionesValores.objects.values_list(
                'CIDVALORCLASIFICACION', 'CVALORCLASIFICACION'
            )
        )

def get_inventory_catalog(is_worker):
    cache_key = 'inventory_catalog'
    data = cache.get(cache_key)
    if data is None:
        data = InventoryRepository.fetch_inventory()

        brand_names = InventoryRepository.fetch_brand_names()
        for product in data:
            brand = brand_names.get(product.pop('CIDVALORCLASIFICACION1'))
            product['brand'] = brand if brand and brand not in NO_BRAND_VALUES else None

        images_by_code = get_images_by_codes([p['CCODIGOPRODUCTO'] for p in data])
        for product in data:
            product['images'] = images_by_code.get(product['CCODIGOPRODUCTO'], [])

        cache.set(cache_key, data, timeout=600)

    # Price visibility is role/resource-aware and computed per request, never
    # cached - the cached catalog above is shared across every requester
    # regardless of who's asking. Prices are private to company workers by
    # default; a product is public only via an explicit ProductPriceVisibility
    # row (see catalog.models - the owner's 2026-09 decision).
    public_codes = get_public_price_codes()
    result = []
    for product in data:
        visible = is_worker or product['CCODIGOPRODUCTO'] in public_codes
        result.append({
            **product,
            'CPRECIO1': product['CPRECIO1'] if visible else None,
            'price_visible': visible,
        })
    return result

from django.core.cache import cache
from .models import AdmProductos
from catalog.services import get_images_by_codes

class InventoryRepository:
    @staticmethod
    def fetch_inventory():
        return list(
            AdmProductos.objects.values(
                'CIDPRODUCTO',
                'CCODIGOPRODUCTO',
                'CNOMBREPRODUCTO',
                'CPRECIO1',
                'CTEXTOEXTRA1'
            )
        )

def get_inventory_catalog():
    cache_key = 'inventory_catalog'
    data = cache.get(cache_key)
    if data is None:
        data = InventoryRepository.fetch_inventory()
        images_by_code = get_images_by_codes([p['CCODIGOPRODUCTO'] for p in data])
        for product in data:
            product['images'] = images_by_code.get(product['CCODIGOPRODUCTO'], [])
        cache.set(cache_key, data, timeout=600)
    return data

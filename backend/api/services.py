from django.core.cache import cache
from .models import AdmProductos

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
        cache.set(cache_key, data, timeout=600)
    return data

from django.http import JsonResponse
from .models import Product

def api_products(request):
    # Consultamos la base de datos y convertimos los registros a una lista de diccionarios
    products = list(Product.objects.values('id', 'name', 'sku', 'price', 'stock'))
    return JsonResponse(products, safe=False)
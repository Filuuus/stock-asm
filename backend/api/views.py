import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Product, StockMovement

def api_products(request):
    # Consultamos la base de datos y convertimos los registros a una lista de diccionarios
    products = list(Product.objects.values('id', 'name', 'sku', 'price', 'stock', 'brand', 'category'))
    return JsonResponse(products, safe=False)

@csrf_exempt
def register_movement(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)

            product = Product.objects.get(sku=data['sku'])

            movment = StockMovement.objects.create(
                product = product,
                movement_type = data['movement_type'],
                quantity = data['quantity'],
                reason = data['reason']
                )

            product.refresh_from_db()

            return JsonResponse ({
                'status': 'success',
                'message': 'Movimiento registrado',
                'new_stock': product.stock
            })
        
        except Product.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Producto no encontrado'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400 )
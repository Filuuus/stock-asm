from rest_framework.decorators import api_view
from rest_framework.response import Response
from .services import get_inventory_catalog, get_product_detail

@api_view(['GET'])
def inventory_list(request):
    return Response(get_inventory_catalog(request.user.is_authenticated))


@api_view(['GET'])
def product_detail(request, code):
    product = get_product_detail(code, request.user.is_authenticated)
    if product is None:
        return Response({'error': 'Producto no encontrado.'}, status=404)
    return Response(product)

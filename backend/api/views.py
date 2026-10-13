from rest_framework.decorators import api_view, permission_classes
from accounts.permissions import IsWorker
from rest_framework.response import Response
from .services import get_inventory_catalog, get_product_detail, search_gea_parts

@api_view(['GET'])
def inventory_list(request):
    return Response(get_inventory_catalog(request.user.is_authenticated))


@api_view(['GET'])
def product_detail(request, key):
    product = get_product_detail(key, request.user.is_authenticated)
    if product is None:
        return Response({'error': 'Producto no encontrado.'}, status=404)
    return Response(product)


# Staff only: it's a lookup by GEA part number, which the public never sees.
@api_view(['GET'])
@permission_classes([IsWorker])
def gea_parts(request):
    return Response(search_gea_parts(request.query_params.get('q', ''), True))

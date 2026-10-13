from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser
from accounts.permissions import IsWorker
from rest_framework.response import Response
from catalog.services import PhotoError, delete_photo, save_photo, set_description
from .services import _catalog, get_inventory_catalog, get_product_detail, search_gea_parts

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


def _code(key):
    return next((p['CCODIGOPRODUCTO'] for p in _catalog(True) if p['key'] == key), None)


# Staff photos from the /fotos page (usually a phone camera).
@api_view(['POST'])
@permission_classes([IsWorker])
@parser_classes([MultiPartParser])
def product_photos(request, key):
    code, upload = _code(key), request.FILES.get('foto')
    if code is None:
        return Response({'error': 'Producto no encontrado.'}, status=404)
    if upload is None:
        return Response({'error': 'Falta la foto.'}, status=400)
    try:
        img = save_photo(code, upload)
    except PhotoError as e:
        return Response({'error': str(e)}, status=400)
    return Response({'id': img.pk, 'file': img.file, 'is_primary': img.is_primary}, status=201)


@api_view(['DELETE'])
@permission_classes([IsWorker])
def product_photo(request, key, pk):
    code = _code(key)
    if code is None or not delete_photo(code, pk):
        return Response(status=404)
    return Response(status=204)


@api_view(['PUT'])
@permission_classes([IsWorker])
def product_description(request, key):
    code = _code(key)
    if code is None:
        return Response({'error': 'Producto no encontrado.'}, status=404)
    try:
        text = set_description(code, request.data.get('text'), request.user)
    except PhotoError as e:
        return Response({'error': str(e)}, status=400)
    return Response({'description': text})

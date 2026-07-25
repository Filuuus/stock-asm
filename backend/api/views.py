from rest_framework.decorators import api_view
from rest_framework.response import Response
from .services import get_inventory_catalog

@api_view(['GET'])
def inventory_list(request):
    return Response(get_inventory_catalog())

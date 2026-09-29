from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsAccountingOrManagement

from .services import invoice_detail, search_invoices


@api_view(['GET'])
@permission_classes([IsAccountingOrManagement])
def invoice_search(request):
    results = search_invoices(request.query_params.get('q', ''))
    if results is None:
        return Response({'error': 'Escriba un No. Factura, por ejemplo "B 20016" o "20016".'}, status=400)
    return Response({'results': results})


@api_view(['GET'])
@permission_classes([IsAccountingOrManagement])
def invoice_detail_view(request, invoice_id):
    detail = invoice_detail(invoice_id)
    if detail is None:
        return Response({'error': 'No existe una factura con ese id.'}, status=404)
    return Response(detail)

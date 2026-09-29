from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsAccountingOrManagement

from .client_history import client_history
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


@api_view(['GET'])
@permission_classes([IsAccountingOrManagement])
def client_history_view(request, client_id):
    history = client_history(client_id, full=request.query_params.get('completo') == '1')
    if history is None:
        return Response({'error': 'No existe un cliente con ese id.'}, status=404)
    return Response(history)

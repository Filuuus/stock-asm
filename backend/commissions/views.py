from datetime import date, datetime

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsManagement, IsWorker

from .models import InvoiceCommissionOverride
from .services import CommissionRepository, calculate_commissions


def _parse_date(value, default):
    if not value:
        return default
    return datetime.strptime(value, '%Y-%m-%d').date()


@api_view(['GET'])
@permission_classes([IsWorker])
def commissions_summary(request):
    today = date.today()
    try:
        date_from = _parse_date(request.query_params.get('date_from'), today.replace(day=1))
        date_to = _parse_date(request.query_params.get('date_to'), today)
    except ValueError:
        return Response({'error': 'date_from/date_to must be YYYY-MM-DD'}, status=400)

    result = calculate_commissions(date_from, date_to)
    return Response(result)


@api_view(['GET'])
@permission_classes([IsManagement])
def invoice_search(request):
    try:
        folio = int(request.query_params.get('folio', ''))
    except ValueError:
        return Response({'error': 'folio debe ser un número.'}, status=400)

    agent_codes = CommissionRepository.fetch_agent_codes()
    results = [
        {
            'invoice_id': f['CIDDOCUMENTO'],
            'folio': f['CFOLIO'],
            'cliente': f['CRAZONSOCIAL'],
            'fecha': f['CFECHA'],
            'total': f['CTOTAL'],
            'zone': agent_codes.get(f['CIDAGENTE']),
        }
        for f in CommissionRepository.search_facturas(folio)
    ]
    return Response(results)


def _serialize_override(override):
    return {
        'invoice_id': override.invoice_id,
        'excluded': override.excluded,
        'override_amount': override.override_amount,
        'zone': override.zone,
        'note': override.note,
    }


@api_view(['POST'])
@permission_classes([IsManagement])
def override_create(request):
    invoice_id = request.data.get('invoice_id')
    excluded = bool(request.data.get('excluded', False))
    override_amount = request.data.get('override_amount')
    override_amount = None if override_amount in (None, '') else override_amount
    zone = request.data.get('zone', '') or ''
    note = request.data.get('note', '') or ''

    if not invoice_id:
        return Response({'error': 'invoice_id es requerido.'}, status=400)
    if not excluded and override_amount is None:
        return Response({'error': 'Debe excluir la factura o indicar un monto manual.'}, status=400)
    if override_amount is not None and not zone:
        return Response({'error': 'Debe indicar la zona para un monto manual.'}, status=400)

    override, _ = InvoiceCommissionOverride.objects.update_or_create(
        invoice_id=invoice_id,
        defaults={
            'excluded': excluded,
            'override_amount': override_amount,
            'zone': zone,
            'note': note,
            'created_by': request.user,
        },
    )
    return Response(_serialize_override(override))


@api_view(['DELETE'])
@permission_classes([IsManagement])
def override_delete(request, invoice_id):
    InvoiceCommissionOverride.objects.filter(invoice_id=invoice_id).delete()
    return Response(status=204)

from datetime import date, datetime

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsAccountingOrManagement

from .models import CorteDeCajaAdjustment
from .services import calculate_corte_de_caja


def _parse_date(value, default=None):
    if not value:
        return default
    return datetime.strptime(value, '%Y-%m-%d').date()


@api_view(['GET'])
@permission_classes([IsAccountingOrManagement])
def corte_de_caja_summary(request):
    today = date.today()
    try:
        date_from = _parse_date(request.query_params.get('date_from'), today)
        date_to = _parse_date(request.query_params.get('date_to'), today)
    except ValueError:
        return Response({'error': 'date_from/date_to must be YYYY-MM-DD'}, status=400)

    result = calculate_corte_de_caja(date_from, date_to)
    return Response(result)


def _serialize_adjustment(adjustment):
    return {
        'invoice_id': adjustment.invoice_id,
        'event_date': adjustment.event_date,
        'payment_method': adjustment.payment_method,
        'reviewed': adjustment.reviewed,
        'reviewed_by': adjustment.reviewed_by.username if adjustment.reviewed_by else None,
        'excluded': adjustment.excluded,
        'note': adjustment.note,
    }


@api_view(['POST'])
@permission_classes([IsAccountingOrManagement])
def adjustment_upsert(request):
    invoice_id = request.data.get('invoice_id')
    event_date_raw = request.data.get('event_date')
    if not invoice_id or not event_date_raw:
        return Response({'error': 'invoice_id y event_date son requeridos.'}, status=400)
    try:
        event_date = _parse_date(event_date_raw)
    except ValueError:
        return Response({'error': 'event_date debe tener formato YYYY-MM-DD.'}, status=400)

    data = request.data
    valid_methods = dict(CorteDeCajaAdjustment.PAYMENT_METHOD_CHOICES)
    defaults = {}
    if 'payment_method' in data:
        payment_method = data['payment_method'] or ''
        if payment_method and payment_method not in valid_methods:
            return Response({'error': 'Forma de pago inválida.'}, status=400)
        defaults['payment_method'] = payment_method
    if 'excluded' in data:
        defaults['excluded'] = bool(data['excluded'])
    if 'note' in data:
        defaults['note'] = data['note'] or ''
    if 'reviewed' in data:
        reviewed = bool(data['reviewed'])
        defaults['reviewed'] = reviewed
        defaults['reviewed_by'] = request.user if reviewed else None
        defaults['reviewed_at'] = timezone.now() if reviewed else None

    adjustment, _ = CorteDeCajaAdjustment.objects.get_or_create(
        invoice_id=invoice_id, event_date=event_date, defaults={'created_by': request.user},
    )
    for field, value in defaults.items():
        setattr(adjustment, field, value)
    adjustment.save()
    return Response(_serialize_adjustment(adjustment))


@api_view(['DELETE'])
@permission_classes([IsAccountingOrManagement])
def adjustment_delete(request, invoice_id, event_date):
    try:
        parsed_date = _parse_date(event_date)
    except ValueError:
        return Response({'error': 'event_date debe tener formato YYYY-MM-DD.'}, status=400)
    CorteDeCajaAdjustment.objects.filter(invoice_id=invoice_id, event_date=parsed_date).delete()
    return Response(status=204)

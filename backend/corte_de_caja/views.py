from datetime import date, datetime

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsAccountingOrManagement
from api.models import AdmDocumentos

from .models import CorteDeCajaAdjustment
from .services import BANK_CODES, CONFIDENCE_HIGH, CONFIDENCE_LOW, CONFIDENCE_MEDIUM, calculate_corte_de_caja


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
        if payment_method:
            # Remember who paid and where, so the suggestion engine can learn
            # this client's habits (bare ERP id only - never the name).
            defaults['client_id'] = AdmDocumentos.objects.filter(pk=invoice_id).values_list(
                'CIDCLIENTEPROVEEDOR', flat=True,
            ).first()
            bank_code = data.get('bank_code') or ''
            defaults['bank_code'] = bank_code if bank_code in BANK_CODES else ''
    if 'excluded' in data:
        # Locked 2026-09-26: excluding a row hides real ERP cash instead of
        # fixing the ERP data that's wrong (e.g. a duplicate poliza) - exactly
        # the kind of manual correction this platform exists to avoid. The
        # model field stays (Django admin can still set it for a genuine
        # emergency), but the accountants' day-to-day workflow can't reach it.
        return Response(
            {'error': 'Un pago no se puede excluir desde aquí. Corrija el dato de origen en Contpaqi.'},
            status=400,
        )
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


@api_view(['POST'])
@permission_classes([IsAccountingOrManagement])
def confirm_suggestions(request):
    """Confirms, in one click, the suggested payment methods in a date range
    that the server itself rates at the requested confidence tier (default:
    only 'alta'). The server decides which rows qualify - the client only says
    which range and how far down the tiers to go - and only unconfirmed,
    non-excluded rows are touched."""
    try:
        date_from = _parse_date(request.data.get('date_from'))
        date_to = _parse_date(request.data.get('date_to'))
    except ValueError:
        return Response({'error': 'date_from/date_to deben tener formato YYYY-MM-DD.'}, status=400)
    if not date_from or not date_to:
        return Response({'error': 'date_from y date_to son requeridos.'}, status=400)
    tiers = request.data.get('tiers') or [CONFIDENCE_HIGH]
    if not isinstance(tiers, list) or not set(tiers) <= {CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW}:
        return Response({'error': 'tiers inválido.'}, status=400)

    confirmed = 0
    total_amount = 0
    for row in calculate_corte_de_caja(date_from, date_to)['rows']:
        if row['excluded'] or row['payment_method_confirmed'] or not row['payment_method']:
            continue
        if row['suggestion_confidence'] not in tiers:
            continue
        adjustment, _ = CorteDeCajaAdjustment.objects.get_or_create(
            invoice_id=row['invoice_id'], event_date=row['event_date'], defaults={'created_by': request.user},
        )
        if adjustment.payment_method:
            continue
        adjustment.payment_method = row['payment_method']
        adjustment.client_id = row['client_id']
        adjustment.bank_code = row['bank_code']
        adjustment.save()
        confirmed += 1
        total_amount += float(row['amount'])
    return Response({'confirmed': confirmed, 'total_amount': total_amount})

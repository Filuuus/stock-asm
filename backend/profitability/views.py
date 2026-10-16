from datetime import date

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsManagement

from .models import ExcludedProduct, ExcludedSaleLine, ProductWeight
from .services import calculate_profitability, product_invoices
from .setup import route_setup, save_route_setup


def _month_start(value):
    year, month = map(int, value.split('-'))
    return date(year, month, 1)


@api_view(['GET'])
@permission_classes([IsManagement])
def profitability(request):
    """?from=YYYY-MM&to=YYYY-MM, both months included; &drop=1,2,3 imagines not selling those products."""
    try:
        first = _month_start(request.query_params['from'])
        last = _month_start(request.query_params['to'])
    except (KeyError, ValueError):
        return Response({'error': 'from y to deben tener formato YYYY-MM.'}, status=400)
    if last < first:
        return Response({'error': 'El periodo termina antes de empezar.'}, status=400)
    try:
        drop = frozenset(int(x) for x in request.query_params.get('drop', '').split(',') if x)
    except ValueError:
        return Response({'error': 'drop debe ser una lista de ids.'}, status=400)
    end = date(last.year + last.month // 12, last.month % 12 + 1, 1)
    return Response(calculate_profitability(first, end, refresh=request.query_params.get('refresh') == '1', drop=drop))


@api_view(['GET'])
@permission_classes([IsManagement])
def invoices(request):
    """?from=YYYY-MM&to=YYYY-MM&product=ID[&client=ID][&zone=ZONA1]"""
    try:
        first = _month_start(request.query_params['from'])
        last = _month_start(request.query_params['to'])
        product = int(request.query_params['product'])
        client = int(request.query_params['client']) if request.query_params.get('client') else None
    except (KeyError, ValueError):
        return Response({'error': 'Parámetros inválidos.'}, status=400)
    end = date(last.year + last.month // 12, last.month % 12 + 1, 1)
    return Response(product_invoices(first, end, product, client, request.query_params.get('zone') or None))


@api_view(['POST'])
@permission_classes([IsManagement])
def set_weight(request):
    """{"product_id": 123, "kg": 2.5}; kg null removes the manual weight."""
    try:
        product_id = int(request.data['product_id'])
        kg = request.data.get('kg')
        kg = None if kg in (None, '') else float(kg)
    except (KeyError, TypeError, ValueError):
        return Response({'error': 'product_id y kg deben ser números.'}, status=400)
    if kg is None:
        ProductWeight.objects.filter(producto_id=product_id).delete()
    elif not 0 <= kg <= 5000:
        return Response({'error': 'El peso debe estar entre 0 y 5,000 kg.'}, status=400)
    else:
        ProductWeight.objects.update_or_create(producto_id=product_id, defaults={'kg': kg, 'updated_by': request.user})
    return Response({'ok': True})


@api_view(['POST'])
@permission_classes([IsManagement])
def set_exclusion(request):
    """{"product_id": 123, "excluded": true}"""
    try:
        product_id = int(request.data['product_id'])
    except (KeyError, TypeError, ValueError):
        return Response({'error': 'product_id debe ser un número.'}, status=400)
    if request.data.get('excluded'):
        ExcludedProduct.objects.get_or_create(producto_id=product_id, defaults={'created_by': request.user})
    else:
        ExcludedProduct.objects.filter(producto_id=product_id).delete()
    return Response({'ok': True})


@api_view(['POST'])
@permission_classes([IsManagement])
def set_line_exclusion(request):
    """{"line_id": 9, "document_id": 1, "product_id": 2, "excluded": true, "folio": "B 123",
    "date": "2026-01-31", "client_id": 3, "reason": "Regalo", "direct": false}; with excluded false only
    line_id is needed. "direct": true marks a direct delivery instead (a sale without weight or route cost)."""
    try:
        line_id = int(request.data['line_id'])
        if request.data.get('excluded'):
            ExcludedSaleLine.objects.update_or_create(
                movement_id=line_id,
                defaults={
                    'document_id': int(request.data['document_id']), 'producto_id': int(request.data['product_id']),
                    'folio': str(request.data['folio'])[:20], 'date': date.fromisoformat(request.data['date']),
                    'client_id': int(request.data['client_id']), 'reason': str(request.data.get('reason', ''))[:60],
                    'direct_delivery': bool(request.data.get('direct')), 'created_by': request.user,
                },
            )
        else:
            ExcludedSaleLine.objects.filter(movement_id=line_id).delete()
    except (KeyError, TypeError, ValueError):
        return Response({'error': 'Datos de la partida inválidos.'}, status=400)
    return Response({'ok': True})


@api_view(['GET', 'PUT'])
@permission_classes([IsManagement])
def setup(request):
    """The route-cost setup: GET it, PUT it back whole."""
    if request.method == 'PUT':
        try:
            save_route_setup(request.data)
        except (ValueError, KeyError, TypeError) as e:
            return Response({'error': str(e) or 'Datos inválidos.'}, status=400)
    return Response(route_setup())

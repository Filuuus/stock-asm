from datetime import date

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsWorker
from catalog.quotes import QuoteError

from .models import ExternalChange, Parlor, ParlorPart
from .services import build_plan, create_service_quote, save_client_phone


@api_view(['GET'])
@permission_classes([IsWorker])
def plan(request):
    """Every registered parlor's parts with their due dates and agenda events, and the next GEA order. Prospects
    (clients we didn't serve this year) come without their parts unless ?prospectos=1: the page folds them, and
    they're most of the data."""
    data = build_plan(timezone.localdate())
    if not request.GET.get('prospectos'):
        data['parlors'] = [p if p['attended'] else {**p, 'parts': [], 'folded': True} for p in data.get('parlors', [])]
    return Response(data)


@api_view(['PUT'])
@permission_classes([IsWorker])
def client_phone(request, code):
    """Staff type a client's phone (Contpaqi's is often missing or a landline); kept locally."""
    if not Parlor.objects.filter(client_code=code).exists():
        return Response(status=404)
    try:
        phone = save_client_phone(code, request.data.get('phone'), request.user)
    except QuoteError as e:
        return Response({'error': str(e)}, status=400)
    return Response({'phone': phone})


@api_view(['POST', 'DELETE'])
@permission_classes([IsWorker])
def contacted(request, pk):
    """Marks a prospect as contacted (POST) or undoes it (DELETE)."""
    parlor = get_object_or_404(Parlor, pk=pk)
    parlor.contacted_at, parlor.contacted_by = (timezone.now(), request.user) if request.method == 'POST' else (None, None)
    parlor.save(update_fields=['contacted_at', 'contacted_by'])
    return Response({'contacted_at': parlor.contacted_at})


@api_view(['POST'])
@permission_classes([IsWorker])
def quote(request, pk):
    """A quote request for the parts picked in this parlor's detail; answers its number for /solicitudes/<id>."""
    try:
        req = create_service_quote(get_object_or_404(Parlor, pk=pk), request.data.get('items'), request.user)
    except QuoteError as e:
        return Response({'error': str(e)}, status=400)
    return Response({'id': req.pk}, status=201)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsWorker])
def part(request, pk):
    """Fixes a part of a parlor's registry: its quantity (the calendars' are often estimates), or removes it
    ("No aplica": the calendar listed a part the parlor doesn't have)."""
    item = get_object_or_404(ParlorPart, pk=pk)
    if request.method == 'DELETE':
        parlor = item.parlor
        if item.code not in parlor.dismissed:
            parlor.dismissed.append(item.code)
            parlor.save(update_fields=['dismissed'])
        item.delete()
        return Response(status=204)
    try:
        quantity = int(request.data.get('quantity'))
    except (TypeError, ValueError):
        quantity = 0
    if not 0 < quantity <= 100000:
        return Response({'error': 'Cantidad no válida.'}, status=400)
    item.quantity = quantity
    item.save(update_fields=['quantity'])
    return Response({'id': item.pk, 'quantity': item.quantity})


@api_view(['POST'])
@permission_classes([IsWorker])
def external_changes(request):
    """Records parts changed by someone else on a day (one part, or a whole category at once): {parts: [part
    ids], day: "YYYY-MM-DD", note}."""
    try:
        day = date.fromisoformat(str(request.data.get('day')))
    except ValueError:
        return Response({'error': 'Fecha no válida.'}, status=400)
    if day > timezone.localdate():
        return Response({'error': 'La fecha no puede ser futura.'}, status=400)
    parts = ParlorPart.objects.filter(pk__in=request.data.get('parts') or [])
    if not parts:
        return Response({'error': 'Elige al menos una pieza.'}, status=400)
    note = str(request.data.get('note') or '').strip()[:200]
    ExternalChange.objects.bulk_create(ExternalChange(part=p, day=day, note=note, created_by=request.user) for p in parts)
    return Response({'created': len(parts)}, status=201)


@api_view(['DELETE'])
@permission_classes([IsWorker])
def external_change(request, pk):
    get_object_or_404(ExternalChange, pk=pk).delete()
    return Response(status=204)

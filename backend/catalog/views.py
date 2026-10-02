from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from accounts.permissions import IsManagement, IsWorker

from . import quotes
from .models import QuoteRequest


class QuoteCreateThrottle(AnonRateThrottle):
    # The public form, per visitor IP (staff aren't limited); keeps a script
    # from flooding the staff list.
    scope = 'quote_create'


def _error(e):
    return Response({'error': str(e)}, status=400)


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
@throttle_classes([])
def quote_requests(request):
    if request.method == 'POST':
        throttle = QuoteCreateThrottle()
        if not throttle.allow_request(request, None):
            return Response({'error': 'Demasiadas solicitudes, intenta más tarde.'}, status=429)
        try:
            req = quotes.create_request(request.data)
        except quotes.QuoteError as e:
            return _error(e)
        return Response({'token': req.token, 'number': req.pk}, status=201)
    if not IsWorker().has_permission(request, None):
        return Response(status=403)
    return Response(quotes.staff_list())


@api_view(['GET'])
@permission_classes([AllowAny])
def quote_public(request, token):
    return Response(quotes.public_view(get_object_or_404(QuoteRequest, token=token)))


@api_view(['GET', 'PUT'])
@permission_classes([IsWorker])
def quote_staff(request, pk):
    req = get_object_or_404(QuoteRequest, pk=pk)
    if request.method == 'PUT':
        try:
            quotes.set_items(req, request.data.get('items'))
        except quotes.QuoteError as e:
            return _error(e)
    return Response(quotes.staff_view(req))


@api_view(['POST'])
@permission_classes([IsManagement])
def quote_decide(request, pk, decision):
    if decision not in ('aprobar', 'rechazar'):
        return Response(status=404)
    req = get_object_or_404(QuoteRequest, pk=pk)
    try:
        if decision == 'aprobar':
            quotes.approve(req, request.user, request.data.get('valid_days', quotes.DEFAULT_VALID_DAYS))
        else:
            quotes.reject(req, request.user)
    except quotes.QuoteError as e:
        return _error(e)
    return Response(quotes.staff_view(req))

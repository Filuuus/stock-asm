from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from accounts.permissions import IsManagement, IsWorker

from . import quotes, rules
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
@permission_classes([IsWorker])
def quote_pending(request):
    """What the badge on the Solicitudes menu link counts."""
    return Response({'nuevas': quotes.pending_count()})


@api_view(['GET'])
@permission_classes([AllowAny])
def quote_public(request, token):
    return Response(quotes.public_view(get_object_or_404(QuoteRequest, token=token)))


@api_view(['POST'])
@permission_classes([AllowAny])
def quote_accept(request, token):
    """The customer approves their quote from its link."""
    req = get_object_or_404(QuoteRequest, token=token)
    try:
        quotes.accept(req)
    except quotes.QuoteError as e:
        return _error(e)
    return Response(quotes.public_view(req))


@api_view(['GET', 'PUT'])
@permission_classes([IsWorker])
def quote_staff(request, pk):
    req = get_object_or_404(QuoteRequest, pk=pk)
    if request.method == 'PUT':
        try:
            quotes.set_items(req, request.data.get('items'), request.user)
        except quotes.QuoteError as e:
            return _error(e)
    return Response(quotes.staff_view(req, request.user))


# What any staff member can do to a request (sharing prices no longer waits on management, 2026-11-07).
STAFF_ACTIONS = {
    'enviar': lambda req, user, data: quotes.send(req, user, data.get('valid_days', quotes.DEFAULT_VALID_DAYS)),
    'vendida': lambda req, user, data: quotes.mark_sold(req, user),
    'reabrir': lambda req, user, data: quotes.reopen(req, user),
    'contactar': lambda req, user, data: quotes.mark_contacted(req, user),
    'deshacer-contacto': lambda req, user, data: quotes.undo_contacted(req, user),
    'tomar': lambda req, user, data: quotes.take(req, user),
    'soltar': lambda req, user, data: quotes.release(req, user),
    'nota': lambda req, user, data: quotes.add_note(req, user, data.get('text')),
    'telefono': lambda req, user, data: quotes.set_phone(req, user, data.get('phone')),
    'descuento': lambda req, user, data: quotes.set_discount(req, user, data.get('discount')),
    'cerrar': lambda req, user, data: quotes.close(req, user, data.get('reason')),
}


@api_view(['POST'])
@permission_classes([IsWorker])
def quote_action(request, pk, action):
    change = STAFF_ACTIONS.get(action)
    if change is None:
        return Response(status=404)
    req = get_object_or_404(QuoteRequest, pk=pk)
    try:
        change(req, request.user, request.data)
    except quotes.QuoteError as e:
        return _error(e)
    return Response(quotes.staff_view(req, request.user))


@api_view(['DELETE'])
@permission_classes([IsWorker])
def quote_note(request, pk, note):
    req = get_object_or_404(QuoteRequest, pk=pk)
    try:
        quotes.delete_note(req, request.user, note)
    except quotes.QuoteError as e:
        return _error(e)
    return Response(quotes.staff_view(req, request.user))


# /ajustes-catalogo: every change returns the whole page's data.
def _rules_response(change, *args):
    try:
        change(*args)
    except rules.RuleError as e:
        return _error(e)
    return Response(rules.overview())


@api_view(['GET'])
@permission_classes([IsManagement])
def rules_overview(request):
    return Response(rules.overview())


@api_view(['POST'])
@permission_classes([IsManagement])
def rules_specials(request):
    return _rules_response(rules.add_special, request.data.get('name'))


@api_view(['PATCH'])
@permission_classes([IsManagement])
def rules_special(request, key):
    return _rules_response(rules.rename_special, key, request.data.get('name'))


@api_view(['PUT'])
@permission_classes([IsManagement])
def rules_hidden(request, key):
    return _rules_response(rules.set_hidden, key, request.data.get('hidden'))


@api_view(['PUT'])
@permission_classes([IsManagement])
def rules_category(request, category):
    return _rules_response(rules.set_category, category, request.data)


@api_view(['PUT'])
@permission_classes([IsManagement])
def rules_brand(request):
    return _rules_response(rules.set_brand, request.data.get('erp_name'), request.data.get('public_name'))

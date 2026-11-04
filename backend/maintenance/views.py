from datetime import date

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsPurchasingOrManagement, IsWorker

from .models import OrderLine, PartChange, Visit
from .services import build_plan, month_start


@api_view(['GET'])
@permission_classes([IsWorker])
def plan(request):
    """Every registered parlor's parts with their due dates, the visits, next proposals, this month's GEA
    order proposal and the alerts."""
    return Response(build_plan(timezone.localdate()))


@api_view(['PATCH'])
@permission_classes([IsWorker])
def update_visit(request, pk):
    """{"date": "YYYY-MM-DD" | null, "status": "scheduled" | "done" | "cancelled", "parts": ["code", ...]}.
    Marking it done records each part changed on the visit's date (all its parts unless `parts` says which)."""
    try:
        visit = Visit.objects.get(pk=pk)
    except Visit.DoesNotExist:
        return Response({'error': 'La visita no existe.'}, status=404)
    try:
        if 'date' in request.data:
            visit.date = date.fromisoformat(request.data['date']) if request.data['date'] else None
    except (TypeError, ValueError):
        return Response({'error': 'date debe tener formato YYYY-MM-DD.'}, status=400)
    status = request.data.get('status', visit.status)
    if status not in dict(Visit.STATUS_CHOICES):
        return Response({'error': 'Estado inválido.'}, status=400)
    if status == 'done' and not visit.date:
        return Response({'error': 'Pon la fecha en que se hizo el servicio.'}, status=400)
    codes = {p['code'] for p in visit.parts}
    changed = set(request.data.get('parts') or codes)
    if not changed <= codes:
        return Response({'error': 'Hay piezas que no son de esta visita.'}, status=400)
    with transaction.atomic():
        visit.changes.all().delete()  # re-marking replaces what an earlier confirmation recorded
        if status == 'done':
            PartChange.objects.bulk_create(
                PartChange(parlor=visit.parlor, code=c, date=visit.date, visit=visit) for c in sorted(changed))
        visit.status = status
        visit.save()
    return Response({'id': visit.id, 'date': visit.date, 'status': visit.status})


@api_view(['GET', 'POST'])
@permission_classes([IsPurchasingOrManagement])
def orders(request):
    """GET: open order lines. POST {"lines": [{"code": "...", "quantity": 10}]}: what was ordered from GEA
    this month."""
    if request.method == 'GET':
        return Response([{'id': o.id, 'month': o.month, 'code': o.code, 'quantity': o.quantity}
                         for o in OrderLine.objects.filter(received_on__isnull=True).order_by('month', 'code')])
    try:
        lines = [(str(x['code']).strip(), int(x['quantity'])) for x in request.data['lines']]
    except (KeyError, TypeError, ValueError):
        return Response({'error': 'lines debe ser una lista de {code, quantity}.'}, status=400)
    if not lines or any(not code or qty <= 0 for code, qty in lines):
        return Response({'error': 'Cada línea necesita código y cantidad mayor a cero.'}, status=400)
    month = month_start(timezone.localdate())
    created = OrderLine.objects.bulk_create(OrderLine(month=month, code=c, quantity=q) for c, q in lines)
    return Response({'created': len(created)}, status=201)


@api_view(['PATCH'])
@permission_classes([IsPurchasingOrManagement])
def receive_order_line(request, pk):
    """{"received": true | false}: the line arrived (it stops counting as on order)."""
    updated = OrderLine.objects.filter(pk=pk).update(
        received_on=timezone.localdate() if request.data.get('received', True) else None)
    if not updated:
        return Response({'error': 'La línea no existe.'}, status=404)
    return Response({'id': pk})

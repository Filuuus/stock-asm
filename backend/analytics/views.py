from datetime import date, timedelta

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsManagement

from .services import calculate_sales


@api_view(['GET'])
@permission_classes([IsManagement])
def sales_summary(request):
    # Defaults to the last complete month - growth on a half-finished month
    # always looks like a drop.
    last_month = date.today().replace(day=1) - timedelta(days=1)
    try:
        year, month = map(int, request.query_params.get('month', f'{last_month:%Y-%m}').split('-'))
        date(year, month, 1)
    except ValueError:
        return Response({'error': 'month debe tener formato YYYY-MM.'}, status=400)
    return Response(calculate_sales(year, month, refresh=request.query_params.get('refresh') == '1'))

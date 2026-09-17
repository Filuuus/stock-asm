from datetime import date, datetime

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .services import calculate_commissions


def _parse_date(value, default):
    if not value:
        return default
    return datetime.strptime(value, '%Y-%m-%d').date()


@api_view(['GET'])
def commissions_summary(request):
    today = date.today()
    date_from = _parse_date(request.query_params.get('date_from'), today.replace(day=1))
    date_to = _parse_date(request.query_params.get('date_to'), today)

    result = calculate_commissions(date_from, date_to)
    return Response(result)

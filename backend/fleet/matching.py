"""What a GPS stop was, from the saved places in the local database: the one set of rules for the Notion
log and the route-sheet reviews. Client names are not stored here (the repo is public): callers resolve
the ids from the ERP.

In order: within BASE_M of a company site it's that site; else the nearest exact client place within CLIENT_M
names it (every client of a shared place: family farms); else the nearest spot someone identified within
SPOT_M. Maps bookmarks without clients and town-level (approximate) places never name a stop."""

from django.db import Error as DatabaseError

from api.models import AdmClientes
from profitability.models import SavedPlace

from .timeline import meters

BASE_M, CLIENT_M, SPOT_M = 400, 300, 150


class StopMatcher:
    def __init__(self, places=None):
        places = [p for p in (places if places is not None else SavedPlace.objects.exclude(lat=None)) if p.lat is not None]
        self.bases = [p for p in places if p.kind == 'base']
        self.clients = [p for p in places if not p.kind and p.client_ids and not p.approximate]
        self.spots = [p for p in places if p.kind == 'spot']

    def match(self, lat, lng):
        """{'kind': 'base' | 'client' | 'spot', 'place': SavedPlace, 'meters': int}, or None for an unknown spot."""
        for kind, places, radius in (('base', self.bases, BASE_M), ('client', self.clients, CLIENT_M),
                                     ('spot', self.spots, SPOT_M)):
            near = min(((meters(lat, lng, p.lat, p.lng), p) for p in places), key=lambda x: x[0], default=None)
            if near and near[0] <= radius:
                return {'kind': kind, 'place': near[1], 'meters': round(near[0])}
        return None


def client_names(ids):
    """{ERP client id: name}; empty when the ERP can't be reached, so a log is still written, unnamed."""
    try:
        return dict(AdmClientes.objects.using('erp').filter(CIDCLIENTEPROVEEDOR__in=set(ids))
                    .values_list('CIDCLIENTEPROVEEDOR', 'CRAZONSOCIAL'))
    except DatabaseError:
        return {}

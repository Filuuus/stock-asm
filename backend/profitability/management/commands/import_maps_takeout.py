from datetime import date

from django.core.management.base import BaseCommand
from django.db import connections

from commissions.models import PuntoVentaClientZone
from commissions.services import FACTURA_DOC_TYPE, ZONE_SCOPE
from profitability.models import SavedPlace
from profitability.places import match_clients, read_takeout, territory

ZONES = ('ZONA1', 'ZONA2')
ZONE_YEARS = 3  # 'invoiced lately' = since January this many years ago


class Command(BaseCommand):
    help = ('Imports saved places from Google Maps Takeout folders, then matches every saved place to ERP '
            'clients by name, using the ZONA1/ZONA2 territory the place is in to settle ambiguous names.')

    def add_arguments(self, parser):
        parser.add_argument('folders', nargs='*')

    def handle(self, folders, **options):
        agents = {ZONE_SCOPE[z]: z for z in ZONES}
        with connections['erp'].cursor() as cursor:
            cursor.execute('SELECT CIDCLIENTEPROVEEDOR, CRAZONSOCIAL FROM admClientes WHERE CTIPOCLIENTE IN (1, 2)')
            clients = [(cid, name or '') for cid, name in cursor.fetchall()]
            # Clients invoiced lately -> the zone that invoices them most; None when only the office or the
            # service team does (zone salespeople run last in the ordering, so they overwrite it).
            cursor.execute(
                'SELECT CIDCLIENTEPROVEEDOR, CIDAGENTE, COUNT(*) FROM admDocumentos WHERE CIDDOCUMENTODE = %s '
                'AND CCANCELADO = 0 AND CFECHA >= %s GROUP BY CIDCLIENTEPROVEEDOR, CIDAGENTE '
                'ORDER BY CASE WHEN CIDAGENTE IN (%s, %s) THEN 1 ELSE 0 END, 3',
                [FACTURA_DOC_TYPE, date(date.today().year - ZONE_YEARS, 1, 1), *agents])
            client_zones = {}
            for cid, agent, _ in cursor.fetchall():
                client_zones[cid] = agents.get(agent)
        for pv in PuntoVentaClientZone.objects.filter(active=True):  # route a Punto de Venta client belongs to
            client_zones[pv.cliente_id] = pv.zone if pv.zone in ZONES else None
        seen = 0
        for folder in folders:
            for place in read_takeout(folder):
                seen += 1
                SavedPlace.objects.update_or_create(url=place['url'], defaults=place)

        places = list(SavedPlace.objects.all())
        auto = [p for p in places if p.matched_by != 'manual']  # never overwrite a match someone set by hand
        for p in auto:  # first pass: names that point to one client put their zone on the map
            p.client_ids = match_clients(p.name, clients)
        labeled = [(p.lat, p.lng, client_zones[p.client_ids[0]]) for p in places
                   if p.lat is not None and len(p.client_ids) == 1 and client_zones.get(p.client_ids[0])]
        for p in auto:
            zone = territory(p.lat, p.lng, labeled) if p.lat is not None else None
            p.client_ids = match_clients(p.name, clients, zone, client_zones)
            p.matched_by = 'auto' if p.client_ids else ''
        SavedPlace.objects.bulk_update(auto, ['client_ids', 'matched_by'])
        matched = [p for p in places if p.client_ids]
        self.stdout.write(
            f'{seen} places read; {len(places)} stored, {sum(p.lat is not None for p in places)} with coordinates, '
            f'{len(matched)} matched to {len({c for p in matched for c in p.client_ids})} clients '
            f'({sum(len(p.client_ids) > 1 for p in matched)} places with several).'
        )

from django.core.management.base import BaseCommand
from django.db import connections

from profitability.models import SavedPlace
from profitability.places import match_client, read_takeout


class Command(BaseCommand):
    help = 'Imports saved places from Google Maps Takeout folders and matches them to ERP clients by name.'

    def add_arguments(self, parser):
        parser.add_argument('folders', nargs='+')

    def handle(self, folders, **options):
        with connections['erp'].cursor() as cursor:
            cursor.execute('SELECT CIDCLIENTEPROVEEDOR, CRAZONSOCIAL FROM admClientes WHERE CTIPOCLIENTE IN (1, 2)')
            clients = [(cid, name or '') for cid, name in cursor.fetchall()]
        seen = 0
        for folder in folders:
            for place in read_takeout(folder):
                seen += 1
                obj, _ = SavedPlace.objects.update_or_create(url=place['url'], defaults=place)
                if obj.matched_by != 'manual':  # never overwrite a match someone set by hand
                    obj.client_id = match_client(obj.name, clients)
                    obj.matched_by = 'auto' if obj.client_id else ''
                    obj.save()
        places = SavedPlace.objects.all()
        self.stdout.write(
            f'{seen} places read; {places.count()} stored, {places.exclude(lat=None).count()} with coordinates, '
            f'{places.exclude(client_id=None).count()} matched to a client.'
        )

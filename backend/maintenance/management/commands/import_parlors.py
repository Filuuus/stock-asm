"""Registers parlors from the service calendars, read by reportes/servicios/parse_calendarios.py (the
calendars and that JSON have client names and stay out of the repo; only ERP codes and numbers are stored).

    manage.py import_parlors ../reportes/servicios/calendarios.json <client code> [<client code> ...]

A client already registered is left alone. A blank quantity is estimated from the parts per stall of the
other calendars; with no basis the part is skipped and listed.
"""
import json
import statistics
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from maintenance.models import Parlor, ParlorPart
from maintenance.services import base_code


class Command(BaseCommand):
    help = 'Registers parlors and their parts from the parsed service calendars.'

    def add_arguments(self, parser):
        parser.add_argument('calendars')
        parser.add_argument('clients', nargs='+')

    def handle(self, calendars, clients, **options):
        sheets = json.loads(open(calendars, encoding='utf-8').read())
        per_stall = defaultdict(list)
        for s in sheets:
            for p in s['parts']:
                if p['code'] and isinstance(p['qty'], (int, float)) and p['qty'] > 0 and s['stalls']:
                    per_stall[base_code(p['code'])].append(p['qty'] / s['stalls'])
        for client in clients:
            if Parlor.objects.filter(client_code=client).exists():
                self.stdout.write(f'{client}: already registered')
                continue
            mine = [s for s in sheets if s['client'] == client]
            if not mine:
                self.stdout.write(f'{client}: no calendar sheet')
                continue
            newest = max(s['book'] for s in mine)
            for s in (s for s in mine if s['book'] == newest):
                self.register(client, s, per_stall)

    @transaction.atomic
    def register(self, client, sheet, per_stall):
        parlor = Parlor.objects.create(client_code=client, stalls=sheet['stalls'] or 0, cows=sheet['cows'],
                                       milking_hours_per_day=sheet['hours_day'])
        parts, skipped = {}, []
        for p in sheet['parts']:
            if not p['code']:
                continue
            code = base_code(p['code'])
            qty = p['qty'] if isinstance(p['qty'], (int, float)) and p['qty'] > 0 else None
            if qty is None and per_stall.get(code) and sheet['stalls']:
                qty = statistics.median(per_stall[code]) * sheet['stalls']
            if qty is None:
                skipped.append(code)
            else:
                parts[code] = parts.get(code, 0) + round(qty)  # a part listed under two groups adds up
        ParlorPart.objects.bulk_create(ParlorPart(parlor=parlor, code=c, quantity=q) for c, q in parts.items() if q)
        self.stdout.write(f'{client}: parlor {parlor.id}, {len(parts)} parts'
                          + (f', no quantity for {", ".join(skipped)}' if skipped else ''))

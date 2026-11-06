"""Registers parlors from the service calendars, read by reportes/servicios/parse_calendarios.py (the
calendars and that JSON have client names and stay out of the repo; only ERP codes and numbers are stored).

    manage.py import_parlors ../reportes/servicios/calendarios.json <client code> [<client code> ...]

A client already registered is left alone. A blank quantity is estimated from the parts per stall of the
other calendars; with no basis the part is skipped and listed. Where a sheet lists two parts that do the same
job in one group (two liners, two long milk hoses), only the one invoiced to the client most recently is kept
(services.one_per_family); the others are listed. A listed liner is swapped for the liner the client changed
to more recently, if any (services.what_they_buy).
"""
import json
import re
import statistics
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from maintenance.models import Parlor, ParlorPart
from api.services import _gea_products
from maintenance.services import (HISTORY_DAYS, base_code, category, fetch_invoice_lines, fetch_products,
                                  merge_purchases, one_per_family, part_family, what_they_buy)


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
        # Every calendar's codes, so a client's purchases of a part another calendar lists count too.
        codes = {base_code(p['code']) for s in sheets for p in s['parts'] if p['code']}
        _, names, _ = fetch_products(codes)
        gea = {base_code(k): v for k, v in _gea_products().items()}
        # A part the ERP doesn't have is named by the calendar's own description.
        descs = {base_code(p['code']): p['desc'] for s in sheets for p in s['parts'] if p['code'] and p['desc']}
        families = {c: part_family(c, names.get(c) or descs.get(c, ''), gea.get(c, {})) for c in codes}
        lines = fetch_invoice_lines(codes, timezone.localdate() - timedelta(days=HISTORY_DAYS))
        purchases = merge_purchases(lines)
        last_invoice = {}
        for client_code, code, day, *_ in lines:
            key = (client_code, code)
            last_invoice[key] = max(last_invoice.get(key, day), day)
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
                self.register(client, s, per_stall, families,
                              {code: day for (c, code), day in last_invoice.items() if c == client},
                              {code: ev for (c, code), ev in purchases.items() if c == client})

    @transaction.atomic
    def register(self, client, sheet, per_stall, families, last_invoice, purchases):
        parlor = Parlor.objects.create(client_code=client, label=sheet.get('label', ''), stalls=sheet['stalls'] or 0,
                                       cows=sheet['cows'], milking_hours_per_day=sheet['hours_day'])
        listed, skipped, sheet_months = [], [], {}
        for p in sheet['parts']:
            if not p['code']:
                continue
            code = base_code(p['code'])
            qty = p['qty'] if isinstance(p['qty'], (int, float)) and p['qty'] > 0 else None
            if qty is None and per_stall.get(code) and sheet['stalls']:
                qty = statistics.median(per_stall[code]) * sheet['stalls']
            if qty is None or round(qty) == 0:
                skipped.append(code)
            else:
                listed.append((category(p['section']), code, round(qty)))
                # "12 meses", "06 meses", "01 Mes"; the 2025 sheets' bare numbers are a lookup, not months.
                m = re.match(r'\s*(\d+)\s*MES', (p['recambio'] or '').upper())
                if m:
                    sheet_months.setdefault(code, int(m[1]))
        kept, dropped = one_per_family(listed, families, last_invoice)
        kept, swaps = what_they_buy(kept, families, purchases)
        parts = defaultdict(int)  # a part in two places (claws and LECC) is a row per place
        for group, code, qty in kept:
            parts[(code, group)] += qty
        ParlorPart.objects.bulk_create(ParlorPart(parlor=parlor, code=c, group=g, quantity=q, sheet_months=sheet_months.get(c))
                                       for (c, g), q in parts.items())
        self.stdout.write(f'{client}: parlor {parlor.id}, {len(parts)} parts'
                          + (f', same job as a kept part: {", ".join(c for _, c, _ in dropped)}' if dropped else '')
                          + (f', buys instead: {", ".join(f"{a} -> {b}" for a, b in swaps)}' if swaps else '')
                          + (f', no quantity for {", ".join(skipped)}' if skipped else ''))

"""Grows the parlor registry from the invoices (services.infer_parlors), so clients the calendars don't have get a
parlor too: a client billed for 48 liners with labor has a 12-stall parlor with that liner. Parts are the service
items: every part on a calendar, and every liner. Shows what it would do; --apply writes it (local database only,
the ERP is only read).

    manage.py sync_parlors [--apply]

With --apply it also closes, as sold, the Servicios quotes whose parts were invoiced since they were quoted, and
creates the Notion calendar task of any approved quote that doesn't have one yet (maintenance.notion_tasks).

Nothing is taken out: parts staff removed ("No aplica") stay out, a deactivated parlor is left alone, and a
client with two parlors only gets its stall count checked by hand.
"""
from collections import Counter, defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from api.services import _gea_products
from clients.services import WALK_IN_CLIENT
from catalog.quotes import close_invoiced
from maintenance.notion_tasks import sync_tasks
from maintenance.models import Parlor, ParlorPart
from maintenance.services import (HISTORY_DAYS, build_plan, LINERS_PER_STALL, base_code, fetch_all_names, fetch_clients,
                                  fetch_invoice_lines, fetch_labor_days, infer_parlors, merge_purchases, part_family,
                                  product_key, same_part_other_model)

LINER_GROUP = 'Colectores'


class Command(BaseCommand):
    help = 'Adds parlors and parts from the invoices (dry run unless --apply).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, apply, **options):
        today = timezone.localdate()
        since = today - timedelta(days=HISTORY_DAYS)
        parlors = list(Parlor.objects.prefetch_related('parts'))
        calendar = {x.code for p in parlors for x in p.parts.all()}
        names = fetch_all_names()
        gea = {base_code(k): v for k, v in _gea_products().items()}
        families = {c: part_family(c, n, gea.get(c, {})) for c, n in names.items()}
        liners = {c for c, f in families.items() if f == 'pezonera'}
        lines = fetch_invoice_lines(calendar | liners, since)
        clients = fetch_clients({l[0] for l in lines})
        lines = [l for l in lines if clients.get(l[0], (None,))[0] != WALK_IN_CLIENT]

        registry = defaultdict(list)
        for p in parlors:
            codes = {x.code for x in p.parts.all()}
            registry[p.client_code].append({'id': p.id, 'active': p.active, 'stalls': p.stalls, 'codes': codes,
                                            'dismissed': set(p.dismissed)})

        def covered(code, codes):
            name, family = names.get(code, ''), families.get(code, code)
            return any((family != code and families.get(c) == family) or product_key(names.get(c, '')) == product_key(name)
                       or same_part_other_model(code, name, c, names.get(c, '')) for c in codes)

        found = infer_parlors(merge_purchases(lines), fetch_labor_days(since), liners, registry, covered, today)

        # Where a part goes and the calendar's RECAMBIO: as the calendars most often have it.
        groups, months = defaultdict(Counter), defaultdict(Counter)
        for p in parlors:
            for x in p.parts.all():
                groups[x.code][x.group] += 1
                if x.sheet_months:
                    months[x.code][x.sheet_months] += 1
        group = lambda c: LINER_GROUP if c in liners else (groups[c].most_common(1)[0][0] if groups[c] else 'Otros')  # noqa: E731
        sheet = lambda c: months[c].most_common(1)[0][0] if months[c] else None  # noqa: E731
        name = lambda client: clients.get(client, (None, ''))[1]  # noqa: E731
        by_id = {p.id: p for p in parlors}

        for client, new in sorted(found['new'].items()):
            self.stdout.write(f'NEW {client} {name(client)}: {new["stalls"]} stalls, '
                              + ', '.join(f'{c} x{q}' for c, q in new['parts'].items()))
        for pid, code, qty in found['add']:
            self.stdout.write(f'ADD parlor {pid} {by_id[pid].client_code} {name(by_id[pid].client_code)}: {code} x{qty}')
        for pid, old, new in found['stalls']:
            self.stdout.write(f'STALLS parlor {pid} {by_id[pid].client_code} {name(by_id[pid].client_code)}: {old} -> {new}')
        self.stdout.write(f'{len(found["new"])} new parlors, {len(found["add"])} parts added, '
                          f'{len(found["stalls"])} stall counts changed' + ('' if apply else ' (dry run)'))
        if apply:
            self.save(found, by_id, liners, group, sheet)
            # Servicios quotes whose parts were invoiced since: closed as sold.
            invoiced = build_plan(today)['invoiced_quotes']
            close_invoiced(invoiced)
            self.stdout.write(f'{len(invoiced)} service quotes closed as sold (invoiced)')
            sync_tasks(self.stdout.write)  # approved quotes whose Notion task failed to be created

    @transaction.atomic
    def save(self, found, by_id, liners, group, sheet):
        for client, new in found['new'].items():
            parlor = Parlor.objects.create(client_code=client, stalls=new['stalls'])
            ParlorPart.objects.bulk_create(ParlorPart(parlor=parlor, code=c, quantity=q, group=group(c),
                                                      sheet_months=sheet(c)) for c, q in new['parts'].items())
        ParlorPart.objects.bulk_create(ParlorPart(parlor=by_id[pid], code=c, quantity=q, group=group(c),
                                                  sheet_months=sheet(c)) for pid, c, q in found['add'])
        for pid, _, stalls in found['stalls']:
            Parlor.objects.filter(pk=pid).update(stalls=stalls)
            ParlorPart.objects.filter(parlor_id=pid, code__in=liners).update(quantity=stalls * LINERS_PER_STALL)

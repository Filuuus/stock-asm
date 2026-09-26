from datetime import date

from django.core.management.base import BaseCommand

from corte_de_caja.models import CorteDeCajaAdjustment
from corte_de_caja.services import calculate_corte_de_caja


class Command(BaseCommand):
    help = (
        'Fills client_id and bank_code on payment-method tags that were created before those fields '
        'existed (e.g. the ones imported from the accountant\'s sheet), so the suggestion engine can '
        'learn from them. Safe to re-run: only rows still missing a client_id are touched.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--from', dest='date_from', default='2026-01-01')
        parser.add_argument('--to', dest='date_to', default=date.today().isoformat())

    def handle(self, *args, **options):
        date_from = date.fromisoformat(options['date_from'])
        date_to = date.fromisoformat(options['date_to'])
        rows = {(r['invoice_id'], r['event_date']): r for r in calculate_corte_de_caja(date_from, date_to)['rows']}
        pending = CorteDeCajaAdjustment.objects.exclude(payment_method='').filter(client_id=None)
        filled = missing = 0
        for adjustment in pending:
            row = rows.get((adjustment.invoice_id, adjustment.event_date))
            if row is None:
                missing += 1
                continue
            adjustment.client_id = row['client_id']
            adjustment.bank_code = row['bank_code']
            adjustment.save(update_fields=['client_id', 'bank_code'])
            filled += 1
        self.stdout.write(f'Filled {filled} tag(s); {missing} had no matching payment in {date_from}..{date_to}.')

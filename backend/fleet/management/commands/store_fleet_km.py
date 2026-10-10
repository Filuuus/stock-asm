from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand

from fleet.services import LOCAL_TZ, store_km


class Command(BaseCommand):
    help = (
        'Saves each GPS unit\'s daily km from Zeek in the local database (independent of Notion). '
        'Meant to run nightly; defaults to yesterday. Safe to re-run: existing days are overwritten.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--from', dest='first', type=date.fromisoformat, help='YYYY-MM-DD (default: yesterday)')
        parser.add_argument('--to', dest='last', type=date.fromisoformat, help='YYYY-MM-DD (default: --from)')

    def handle(self, *args, **options):
        first = options['first'] or datetime.now(LOCAL_TZ).date() - timedelta(days=1)
        store_km(first, options['last'] or first, self.stdout.write)

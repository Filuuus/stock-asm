from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand

from fleet.services import LOCAL_TZ, rescue_notion_stops, store_km


class Command(BaseCommand):
    help = (
        'Saves each GPS unit\'s daily km and stops from Zeek in the local database (independent of Notion). '
        'Meant to run nightly (Zeek keeps only ~6 days); defaults to yesterday. Safe to re-run: existing days '
        'are overwritten. --from-notion instead rescues stops and km of older days from the fleet log pages.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--from', dest='first', type=date.fromisoformat, help='YYYY-MM-DD (default: yesterday)')
        parser.add_argument('--to', dest='last', type=date.fromisoformat, help='YYYY-MM-DD (default: --from)')
        parser.add_argument('--from-notion', action='store_true', help='rescue stops and km from Notion daily log pages')

    def handle(self, *args, **options):
        if options['from_notion']:
            return rescue_notion_stops(self.stdout.write)
        first = options['first'] or datetime.now(LOCAL_TZ).date() - timedelta(days=1)
        store_km(first, options['last'] or first, self.stdout.write)

from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand

from fleet.services import LOCAL_TZ, rescue_notion_stops, store_km


class Command(BaseCommand):
    help = (
        'Saves each GPS unit\'s daily km and stops from Zeek in the local database (independent of Notion). '
        'Meant to run nightly (Zeek keeps only ~6 days); defaults to the day before yesterday through yesterday, '
        're-checking the earlier day for trips Zeek reported late. Safe to re-run: a stored day is only replaced '
        'by at least as many km. --from-notion instead rescues stops and km of older days from the fleet log pages.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--from', dest='first', type=date.fromisoformat,
                            help='YYYY-MM-DD (default: the day before yesterday)')
        parser.add_argument('--to', dest='last', type=date.fromisoformat,
                            help='YYYY-MM-DD (default: --from if given, else yesterday)')
        parser.add_argument('--from-notion', action='store_true', help='rescue stops and km from Notion daily log pages')

    def handle(self, *args, **options):
        if options['from_notion']:
            return rescue_notion_stops(self.stdout.write)
        yesterday = datetime.now(LOCAL_TZ).date() - timedelta(days=1)
        if options['first']:
            store_km(options['first'], options['last'] or options['first'], self.stdout.write)
        else:
            store_km(yesterday - timedelta(days=1), options['last'] or yesterday, self.stdout.write)

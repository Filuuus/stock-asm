from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand

from fleet.services import LOCAL_TZ, sync_day


class Command(BaseCommand):
    help = (
        'Writes each vehicle\'s Zeek GPS trips for one day to the Notion fleet log and adds the '
        'day\'s km to its odometer card. Meant to run nightly; defaults to yesterday plus a re-check '
        'of the day before (Zeek sometimes reports a vehicle\'s trips late). Safe to re-run: vehicles '
        'already logged for that day are skipped.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--date', type=date.fromisoformat,
                            help='YYYY-MM-DD (default: the day before yesterday, then yesterday)')

    def handle(self, *args, **options):
        yesterday = datetime.now(LOCAL_TZ).date() - timedelta(days=1)
        for day in [options['date']] if options['date'] else [yesterday - timedelta(days=1), yesterday]:
            sync_day(day, self.stdout.write)

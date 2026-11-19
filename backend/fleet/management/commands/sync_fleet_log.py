from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand, CommandError

from fleet.services import LOCAL_TZ, refresh_names, rewrite_day, sync_day


class Command(BaseCommand):
    help = (
        'Writes each vehicle\'s Zeek GPS trips for one day to the Notion fleet log and adds the '
        'day\'s km to its odometer card. Meant to run nightly; defaults to yesterday plus a re-check '
        'of the day before (Zeek sometimes reports a vehicle\'s trips late). Safe to re-run: vehicles '
        'already logged for that day are skipped. --rewrite redoes an already logged day\'s callouts from '
        'Zeek (only while Zeek still has it); --refresh-names re-names the stops on a month\'s pages still in '
        'Notion from the saved places as they are now. Neither touches km or odometers.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--date', type=date.fromisoformat,
                            help='YYYY-MM-DD (default: the day before yesterday, then yesterday)')
        parser.add_argument('--rewrite', action='store_true', help='rewrite --date\'s pages from Zeek')
        parser.add_argument('--vehicle', help='with --rewrite: only this vehicle (its Notion card name)')
        parser.add_argument('--refresh-names', action='store_true',
                            help='re-name the stops on the pages of yesterday\'s month (or --date\'s)')

    def handle(self, *args, **options):
        yesterday = datetime.now(LOCAL_TZ).date() - timedelta(days=1)
        if options['rewrite']:
            if not options['date']:
                raise CommandError('--rewrite needs --date')
            return rewrite_day(options['date'], options['vehicle'], self.stdout.write)
        if options['refresh_names']:
            first = (options['date'] or yesterday).replace(day=1)
            last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            return refresh_names(first, last, self.stdout.write)
        for day in [options['date']] if options['date'] else [yesterday - timedelta(days=1), yesterday]:
            sync_day(day, self.stdout.write)

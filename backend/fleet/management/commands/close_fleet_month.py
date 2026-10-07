import calendar
from datetime import date

from django.core.management.base import BaseCommand

from fleet.services import close_month


class Command(BaseCommand):
    help = (
        'Adds a "Reporte Mensual" entry per vehicle to the Notion fleet log, summing its daily '
        'entries. Defaults to the previous month, so it can run on the 1st.'
    )

    def add_arguments(self, parser):
        previous = date.today().replace(day=1) - date.resolution
        parser.add_argument('--year', type=int, default=previous.year)
        parser.add_argument('--month', type=int, default=previous.month)

    def handle(self, *args, **options):
        year, month = options['year'], options['month']
        close_month(date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]), self.stdout.write)

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from corte_de_caja.exports import EARLIEST_EXPORT_MONTH, export_month


class Command(BaseCommand):
    help = (
        'Regenerates the Corte de Caja monthly workbook in CORTE_DE_CAJA_EXPORT_DIR. '
        'Meant to be run on a schedule (cron / Windows Task Scheduler) - each run '
        'fully overwrites that month\'s file with the current data, so it is always '
        'safe to re-run. Defaults to the current month.'
    )

    def add_arguments(self, parser):
        today = date.today()
        parser.add_argument('--year', type=int, default=today.year)
        parser.add_argument('--month', type=int, default=today.month)

    def handle(self, *args, **options):
        year, month = options['year'], options['month']
        if date(year, month, 1) < EARLIEST_EXPORT_MONTH:
            raise CommandError(
                f'{year}-{month:02d} is before {EARLIEST_EXPORT_MONTH:%Y-%m} - this replaces the '
                'manual process going forward only, it does not backfill history.'
            )

        path = export_month(year, month)
        self.stdout.write(self.style.SUCCESS(f'Wrote {path}'))

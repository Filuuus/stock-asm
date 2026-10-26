from datetime import date

from django.core.management.base import BaseCommand, CommandError

from corte_de_caja.exports import EARLIEST_EXPORT_MONTH, export_month, export_recent_months


class Command(BaseCommand):
    help = (
        'Regenerates the Corte de Caja monthly workbooks in CORTE_DE_CAJA_EXPORT_DIR/<year>/: this month '
        'and last month by default, or one month with --year and --month. Each run fully overwrites the '
        'file, so it is always safe to re-run (the agrostma-corte-export timer runs it every 15 minutes).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int)
        parser.add_argument('--month', type=int)

    def handle(self, *args, **options):
        year, month = options['year'], options['month']
        if year is None and month is None:
            results = export_recent_months()
        else:
            today = date.today()
            year, month = year or today.year, month or today.month
            if date(year, month, 1) < EARLIEST_EXPORT_MONTH:
                raise CommandError(
                    f'{year}-{month:02d} is before {EARLIEST_EXPORT_MONTH:%Y-%m} - this replaces the '
                    'manual process going forward only, it does not backfill history.'
                )
            results = [{'month': f'{year}-{month:02d}', 'path': str(export_month(year, month))}]
        for r in results:
            if 'path' in r:
                self.stdout.write(self.style.SUCCESS(f"Wrote {r['path']}"))
            else:
                self.stderr.write(f"{r['month']}: {r['error']}")

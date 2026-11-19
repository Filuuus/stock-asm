from django.core.management.base import BaseCommand

from commissions.exports import export_month, export_recent_months


class Command(BaseCommand):
    help = (
        'Regenerates the Comisiones workbooks in COMISIONES_EXPORT_DIR/<year>/: this month and last month by '
        'default, or one month with --year and --month (run by the agrostma-corte-export timer).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int)
        parser.add_argument('--month', type=int)

    def handle(self, *args, **options):
        if options['year'] and options['month']:
            results = [{'month': f"{options['year']}-{options['month']:02d}",
                        'path': str(export_month(options['year'], options['month']))}]
        else:
            results = export_recent_months()
        for r in results:
            if 'path' in r:
                self.stdout.write(self.style.SUCCESS(f"Wrote {r['path']}"))
            else:
                self.stderr.write(f"{r['month']}: {r['error']}")

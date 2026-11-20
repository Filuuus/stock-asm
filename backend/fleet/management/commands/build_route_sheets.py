from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand

from corte_de_caja.exports import ExportFileInUse
from fleet.notion import notion, page_title
from fleet.route_sheets import export_month
from fleet.zeek import LOCAL_TZ


class Command(BaseCommand):
    help = (
        'Writes the monthly route sheets (ZONA 1, ZONA 2, SERVICIOS, OTRAS UNIDADES, PENDIENTES) from the GPS stops '
        'and the ERP to ROUTE_SHEETS_EXPORT_DIR/<year>/, up to yesterday. Defaults to yesterday\'s month, plus the '
        'month before during the first days of a month (its last days\' invoices are entered late). Run after '
        'store_fleet_km. Before rewriting a month\'s file it saves what was typed in its PENDIENTES (¿QUÉ ES?) as places, '
        'so those stops come out named.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int)
        parser.add_argument('--month', type=int)

    def handle(self, *args, **options):
        yesterday = datetime.now(LOCAL_TZ).date() - timedelta(days=1)
        if options['month']:
            months = [(options['year'] or yesterday.year, options['month'])]
        else:
            months = [(yesterday.year, yesterday.month)]
            if yesterday.day <= 4:
                before = yesterday.replace(day=1) - timedelta(days=1)
                months.insert(0, (before.year, before.month))
        units = {imei: page_title(notion('GET', f'pages/{card}')) for imei, card in settings.ZEEK_FLEET.items()}
        for year, month in months:
            try:
                path, learned = export_month(year, month, units)
                self.stdout.write(f'Escrito {path}' + (f' ({learned} respuestas de PENDIENTES guardadas)' if learned else ''))
            except ExportFileInUse:
                self.stderr.write(f'{year}-{month:02d}: el archivo está abierto en Excel; se actualizará en la siguiente corrida.')

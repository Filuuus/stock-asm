from decimal import Decimal

from django.db import migrations

# Names in the accountant's workbook, normalized. Hilux 5 and the Fiat are general-purpose cars (IT
# visits and the like, user 2026-10-10), not route costs. Hilux 4's premium from the 2026 policy table
# (HDI, renewed 16-10-25).
SHEET_NAMES = {
    'Hilux 1': 'HILUX1', 'Hilux 2': 'HILUX2', 'Isuzu bodega': 'ISUZU', 'Montacargas': 'MONTACARGAS',
    'Hilux 4 Servicios': 'HILUX4',
}


def update(apps, schema_editor):
    Vehicle = apps.get_model('profitability', 'PoolVehicle')
    for name, sheet in SHEET_NAMES.items():
        Vehicle.objects.filter(name=name).update(sheet_name=sheet)
    Vehicle.objects.filter(name='Hilux 4 Servicios').update(annual_insurance=Decimal('6699.75'))
    Vehicle.objects.filter(name='Hilux 5').delete()


class Migration(migrations.Migration):
    dependencies = [('profitability', '0006_vehicle_reports')]
    operations = [migrations.RunPython(update, migrations.RunPython.noop)]

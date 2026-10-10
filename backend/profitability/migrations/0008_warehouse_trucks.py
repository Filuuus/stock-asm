from decimal import Decimal

from django.db import migrations

# Management, 2026-10-10: Hilux 8 mostly stays at the warehouse and delivers the big fans; the Isuzu 4.5
# (F-350's replacement, big hauls only) also serves the warehouse. Premiums from the 2026 policy table.
# The workbook logs the Isuzu 4.5 as "ISUZU", added to the warehouse Isuzu's figures - same pool - so its
# row carries only the insurance. The Changan, the F-350 and the forklift's (missing) insurance stay out.


def add(apps, schema_editor):
    Vehicle = apps.get_model('profitability', 'PoolVehicle')
    Vehicle.objects.get_or_create(name='Hilux 8', defaults={
        'pool': 'ALMACEN', 'sheet_name': 'HILUX8', 'maintenance_account': '500511009',
        'km_per_liter': Decimal('8.53'), 'price_per_liter': Decimal('20.76'), 'annual_insurance': Decimal('20665.50'),
    })
    Vehicle.objects.get_or_create(name='Isuzu 4.5', defaults={'pool': 'ALMACEN', 'annual_insurance': Decimal('43728.39')})


def remove(apps, schema_editor):
    apps.get_model('profitability', 'PoolVehicle').objects.filter(name__in=['Hilux 8', 'Isuzu 4.5']).delete()


class Migration(migrations.Migration):
    dependencies = [('profitability', '0007_vehicle_sheet_names')]
    operations = [migrations.RunPython(add, remove)]

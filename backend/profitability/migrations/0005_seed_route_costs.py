from decimal import Decimal

from django.db import migrations

# Confirmed for the Bionat report (2026-10-07/09): payroll ids per route, ledger maintenance account per
# vehicle (matched by plate), insurance premiums from the accountant's policy table, $25k/month warehouse
# rent (not in the ledger). km/L from the accountant's 2026 odometer/liters log; price per liter from
# Sep 2026 loads (gasoline 20.76, diesel 23.33). GPS IMEIs are set locally, never committed.
EMPLOYEES = [(2107, 'ZONA1'), (2110, 'ZONA2'), (93, 'ALMACEN'), (12, 'SERVICIOS'), (2115, 'SERVICIOS')]
VEHICLES = [
    # name, pool, maintenance account, uses LP, km/L, $/L, yearly insurance
    ('Hilux 1', 'ZONA1', '500511011', True, None, None, '18354.32'),
    ('Hilux 2', 'ZONA2', '500511010', False, '7.17', '20.76', '18535.88'),
    ('Isuzu bodega', 'ALMACEN', '500511006', False, '7.39', '23.33', '19062.40'),
    ('Montacargas', 'ALMACEN', '500511007', False, None, None, '0'),
    ('Hilux 4 Servicios', 'SERVICIOS', '500511004', False, '8.91', '20.76', '0'),
    ('Hilux 5', 'SERVICIOS', '500511008', False, '7.45', '20.76', '0'),
]


def seed(apps, schema_editor):
    Employee = apps.get_model('profitability', 'PoolEmployee')
    Vehicle = apps.get_model('profitability', 'PoolVehicle')
    Monthly = apps.get_model('profitability', 'PoolMonthlyCost')
    for employee_id, pool in EMPLOYEES:
        Employee.objects.get_or_create(employee_id=employee_id, defaults={'pool': pool})
    for name, pool, account, lp, kmpl, price, insurance in VEHICLES:
        Vehicle.objects.get_or_create(name=name, defaults={
            'pool': pool, 'maintenance_account': account, 'uses_lp': lp,
            'km_per_liter': Decimal(kmpl) if kmpl else None, 'price_per_liter': Decimal(price) if price else None,
            'annual_insurance': Decimal(insurance),
        })
    Monthly.objects.get_or_create(label='Renta de bodega', defaults={'pool': 'ALMACEN', 'monthly_amount': Decimal('25000')})


def unseed(apps, schema_editor):
    for model in ('PoolEmployee', 'PoolVehicle', 'PoolMonthlyCost'):
        apps.get_model('profitability', model).objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [('profitability', '0004_route_costs')]
    operations = [migrations.RunPython(seed, unseed)]

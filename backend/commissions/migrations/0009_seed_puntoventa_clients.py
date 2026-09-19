from django.db import migrations

# Matched from the 2026 commission tracking spreadsheet (a client only shows
# up under a salesman's sheet if that salesman actually visited them) and
# cross-checked against real invoice history (see project notes, 2026-09-19)
# - not exhaustive, meant to be filled in via the admin as the remaining
# Punto de Venta subdistributors get confirmed.
#
# Deliberately just (cliente_id, zone): see PuntoVentaClientZone's docstring
# for why no client name is stored here - a bare ERP id is meaningless
# without database access, so this is safe to keep in source control even
# though the repo is public.
CLIENTS = [
    (57, 'ZONA1'),
    (68, 'ZONA1'),
    (124, 'ZONA1'),
    (406, 'ZONA1'),
    (565, 'ZONA1'),
    (632, 'ZONA1'),
    (777, 'ZONA1'),
    (788, 'ZONA1'),
    (929, 'ZONA1'),
    (990, 'ZONA2'),
    (1053, 'ZONA1'),
    (1086, 'ZONA2'),
    (1160, 'ZONA1'),
    (1301, 'ZONA1'),
    (1368, 'ZONA1'),
    (1445, 'ZONA2'),
]


def seed(apps, schema_editor):
    PuntoVentaClientZone = apps.get_model('commissions', 'PuntoVentaClientZone')
    for cliente_id, zone in CLIENTS:
        PuntoVentaClientZone.objects.update_or_create(
            cliente_id=cliente_id,
            defaults={
                'zone': zone,
                'note': 'Matched from the 2026 commission tracking spreadsheet',
            },
        )


def unseed(apps, schema_editor):
    PuntoVentaClientZone = apps.get_model('commissions', 'PuntoVentaClientZone')
    PuntoVentaClientZone.objects.filter(cliente_id__in=[c[0] for c in CLIENTS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('commissions', '0008_drop_cliente_nombre'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]

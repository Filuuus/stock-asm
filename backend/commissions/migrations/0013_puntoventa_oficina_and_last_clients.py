from django.db import migrations, models

# The last Punto de Venta clients with invoices in the past 12 months,
# assigned by management 2026-09-30. Bare ERP ids only (see
# PuntoVentaClientZone's docstring: the repo is public).
CLIENTS = [
    (826, 'OFICINA'),
    (408, 'OFICINA'),
    (933, 'OFICINA'),
    (60, 'OFICINA'),
    (1476, 'ZONA1'),
    (82, 'ZONA1'),
    (1381, 'ZONA2'),
    (21, 'ZONA2'),
]


def seed(apps, schema_editor):
    PuntoVentaClientZone = apps.get_model('commissions', 'PuntoVentaClientZone')
    for cliente_id, zone in CLIENTS:
        PuntoVentaClientZone.objects.update_or_create(
            cliente_id=cliente_id,
            defaults={'zone': zone, 'note': 'Assigned by management 2026-09-30'},
        )


def unseed(apps, schema_editor):
    PuntoVentaClientZone = apps.get_model('commissions', 'PuntoVentaClientZone')
    PuntoVentaClientZone.objects.filter(cliente_id__in=[c[0] for c in CLIENTS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('commissions', '0012_seed_mipro_and_bovifit_rates'),
    ]

    operations = [
        migrations.AlterField(
            model_name='puntoventaclientzone',
            name='zone',
            field=models.CharField(
                choices=[('ZONA1', 'Zona 1'), ('ZONA2', 'Zona 2'), ('OFICINA', 'Oficina')], max_length=10,
            ),
        ),
        migrations.RunPython(seed, unseed),
    ]

from django.db import migrations

RATES = [
    # code, label, base_rate, decay_rate_per_week
    ('R', 'Refacciones', '0.0600', '0.0050'),
    ('B', 'Bionat', '0.0200', '0.0050'),
    ('EQ', 'Equipo', '0.0400', '0.0050'),
    # Servicios: rate depends on who performs it, not on the item alone.
    ('S_SALESPERSON', 'Servicios (realizado por ruta ZONA1/ZONA2)', '0.0000', '0.0000'),
    ('S_SERVICIOS', 'Servicios (realizado por cuadrilla SERVICIOS)', '0.0600', '0.0050'),
]

ZERO_COMMISSION_PRODUCTS = [
    ('C-T-M', 'CAJA DE TOALLAS MOCAMBO CAFE - venta a costo / retención de cliente, sin comisión'),
]


def seed(apps, schema_editor):
    CommissionCategoryRate = apps.get_model('commissions', 'CommissionCategoryRate')
    ZeroCommissionProduct = apps.get_model('commissions', 'ZeroCommissionProduct')

    for code, label, base_rate, decay_rate_per_week in RATES:
        CommissionCategoryRate.objects.update_or_create(
            code=code,
            defaults={
                'label': label,
                'base_rate': base_rate,
                'decay_rate_per_week': decay_rate_per_week,
            },
        )

    for producto_codigo, note in ZERO_COMMISSION_PRODUCTS:
        ZeroCommissionProduct.objects.update_or_create(
            producto_codigo=producto_codigo,
            defaults={'note': note},
        )


def unseed(apps, schema_editor):
    CommissionCategoryRate = apps.get_model('commissions', 'CommissionCategoryRate')
    ZeroCommissionProduct = apps.get_model('commissions', 'ZeroCommissionProduct')
    CommissionCategoryRate.objects.filter(code__in=[r[0] for r in RATES]).delete()
    ZeroCommissionProduct.objects.filter(
        producto_codigo__in=[p[0] for p in ZERO_COMMISSION_PRODUCTS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('commissions', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]

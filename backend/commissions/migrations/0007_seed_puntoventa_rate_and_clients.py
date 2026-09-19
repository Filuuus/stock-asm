from django.db import migrations

RATE_CODE = 'PUNTOVENTA'
RATE_LABEL = 'Punto de Venta (subdistribuidores)'
BASE_RATE = '0.0050'
DECAY_RATE_PER_WEEK = '0.0050'


def seed(apps, schema_editor):
    CommissionCategoryRate = apps.get_model('commissions', 'CommissionCategoryRate')
    CommissionCategoryRate.objects.update_or_create(
        code=RATE_CODE,
        defaults={'label': RATE_LABEL, 'base_rate': BASE_RATE, 'decay_rate_per_week': DECAY_RATE_PER_WEEK},
    )


def unseed(apps, schema_editor):
    CommissionCategoryRate = apps.get_model('commissions', 'CommissionCategoryRate')
    CommissionCategoryRate.objects.filter(code=RATE_CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('commissions', '0006_puntoventa_client_zone'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]

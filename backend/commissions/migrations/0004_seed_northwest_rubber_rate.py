from django.db import migrations

CODE = 'R_NW'
LABEL = 'Refacciones (North West Rubber)'
BASE_RATE = '0.0400'
DECAY_RATE_PER_WEEK = '0.0050'


def seed(apps, schema_editor):
    CommissionCategoryRate = apps.get_model('commissions', 'CommissionCategoryRate')
    CommissionCategoryRate.objects.update_or_create(
        code=CODE,
        defaults={'label': LABEL, 'base_rate': BASE_RATE, 'decay_rate_per_week': DECAY_RATE_PER_WEEK},
    )


def unseed(apps, schema_editor):
    CommissionCategoryRate = apps.get_model('commissions', 'CommissionCategoryRate')
    CommissionCategoryRate.objects.filter(code=CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('commissions', '0003_alter_commissioncategoryrate_decay_rate_per_week'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]

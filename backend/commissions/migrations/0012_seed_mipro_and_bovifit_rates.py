from django.db import migrations

RATES = [
    # code, label, base_rate, decay_rate_per_week - confirmed by management 2026-09-30
    ('B_MIPRO', 'Bionat (Mipro)', '0.0100', '0.0050'),
    ('B_BOVI', 'Bionat (Bovifit)', '0.0400', '0.0050'),
]


def seed(apps, schema_editor):
    CommissionCategoryRate = apps.get_model('commissions', 'CommissionCategoryRate')
    for code, label, base_rate, decay_rate_per_week in RATES:
        CommissionCategoryRate.objects.update_or_create(
            code=code,
            defaults={'label': label, 'base_rate': base_rate, 'decay_rate_per_week': decay_rate_per_week},
        )


def unseed(apps, schema_editor):
    CommissionCategoryRate = apps.get_model('commissions', 'CommissionCategoryRate')
    CommissionCategoryRate.objects.filter(code__in=[r[0] for r in RATES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('commissions', '0011_commissioncategoryrate_late_penalty'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]

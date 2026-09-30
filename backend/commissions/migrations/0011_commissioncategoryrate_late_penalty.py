from decimal import Decimal

from django.db import migrations, models

# The 6% GEA parts pay 6% only when paid on time; late, they start at 4%
# (confirmed by management 2026-09-30).
R_LATE_PENALTY = Decimal('0.0150')


def seed(apps, schema_editor):
    apps.get_model('commissions', 'CommissionCategoryRate').objects.filter(code='R').update(late_penalty=R_LATE_PENALTY)


def unseed(apps, schema_editor):
    apps.get_model('commissions', 'CommissionCategoryRate').objects.filter(code='R').update(late_penalty=Decimal('0'))


class Migration(migrations.Migration):

    dependencies = [
        ('commissions', '0010_invoicecommissionoverride'),
    ]

    operations = [
        migrations.AddField(
            model_name='commissioncategoryrate',
            name='late_penalty',
            field=models.DecimalField(decimal_places=4, default=Decimal('0'), max_digits=5),
        ),
        migrations.RunPython(seed, unseed),
    ]

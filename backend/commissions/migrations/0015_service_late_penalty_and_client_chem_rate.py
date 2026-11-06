from decimal import Decimal

from django.db import migrations

# Management 2026-11-06: crew service labor pays 6% on time and 4% once late
# (then the weekly decay), like the R parts; and the crew's chemical sales to
# one client (see services.SERVICE_CHEM_CLIENT_IDS) start at 2%.


def seed(apps, schema_editor):
    Rate = apps.get_model('commissions', 'CommissionCategoryRate')
    Rate.objects.filter(code='S_SERVICIOS').update(late_penalty=Decimal('0.0150'))
    Rate.objects.update_or_create(code='S_CHEM_CLIENT', defaults={
        'label': 'Químicos de Servicios a cliente específico', 'base_rate': Decimal('0.0200'),
        'decay_rate_per_week': Decimal('0.0050'), 'late_penalty': Decimal('0')})


def unseed(apps, schema_editor):
    Rate = apps.get_model('commissions', 'CommissionCategoryRate')
    Rate.objects.filter(code='S_SERVICIOS').update(late_penalty=Decimal('0'))
    Rate.objects.filter(code='S_CHEM_CLIENT').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('commissions', '0014_line_rates_and_pv_products'),
    ]

    operations = [migrations.RunPython(seed, unseed)]

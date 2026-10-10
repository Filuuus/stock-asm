from django.db import migrations

# ERP product 2848 = code 0001 "EQUIPO DE ORDEÑO COMPLETO": a complete milking system resold once
# (F-19417, Dec 2025, $4.57M). Management asked to leave it out (2026-10-10).
PRODUCT_ID = 2848


def seed(apps, schema_editor):
    apps.get_model('profitability', 'ExcludedProduct').objects.get_or_create(producto_id=PRODUCT_ID)


def unseed(apps, schema_editor):
    apps.get_model('profitability', 'ExcludedProduct').objects.filter(producto_id=PRODUCT_ID).delete()


class Migration(migrations.Migration):
    dependencies = [('profitability', '0002_excludedproduct')]
    operations = [migrations.RunPython(seed, unseed)]

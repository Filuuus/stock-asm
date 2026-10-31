from django.db import migrations

# Mats bought only from a distributor, each a duplicate of one we stock (user, 2026-10-16).
HIDDEN = [2566, 2568, 2569]
# category, show_price, on_order, hide_brand: the rules as they stood in code (owner, 2026-10-13).
CATEGORIES = [
    ('R', True, 'NEVER', False), ('R_NW', True, 'ALWAYS', False), ('R_CHEM', False, 'NEVER', True),
    ('R_FAN', False, 'ALWAYS', False), ('B', True, 'IF_SOLD', False), ('S', False, 'NEVER', False),
]
BRANDS = {
    'GEA FARM TECHNOLOGIES': 'GEA', 'BIONAT-SANO, SA DE CV': 'Bionat',
    'NORTH WEST RUBBER': 'North West Rubber', 'VES-ARTEX': 'VES-Artex',
}


def seed(apps, schema_editor):
    get = apps.get_model
    get('catalog', 'HiddenProduct').objects.bulk_create(get('catalog', 'HiddenProduct')(product_id=i) for i in HIDDEN)
    for category, show_price, on_order, hide_brand in CATEGORIES:
        get('catalog', 'CategoryRule').objects.create(
            category=category, show_price=show_price, on_order=on_order, hide_brand=hide_brand)
    for erp_name, public_name in BRANDS.items():
        get('catalog', 'BrandRule').objects.create(erp_name=erp_name, public_name=public_name)


class Migration(migrations.Migration):
    dependencies = [('catalog', '0006_catalog_rules')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]

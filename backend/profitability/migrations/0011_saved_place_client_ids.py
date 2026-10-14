from django.db import migrations, models


def copy_client_id(apps, schema_editor):
    SavedPlace = apps.get_model('profitability', 'SavedPlace')
    for place in SavedPlace.objects.exclude(client_id=None):
        place.client_ids = [place.client_id]
        place.save(update_fields=['client_ids'])


class Migration(migrations.Migration):

    dependencies = [
        ('profitability', '0010_excluded_sale_lines'),
    ]

    operations = [
        migrations.AddField(
            model_name='savedplace',
            name='client_ids',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(copy_client_id, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='savedplace',
            name='client_id',
        ),
    ]

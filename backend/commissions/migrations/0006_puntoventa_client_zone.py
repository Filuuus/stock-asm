from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('commissions', '0005_seed_chemicals_and_fans_rate'),
    ]

    operations = [
        migrations.CreateModel(
            name='PuntoVentaClientZone',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cliente_id', models.IntegerField(unique=True)),
                ('cliente_nombre', models.CharField(blank=True, max_length=200)),
                ('zone', models.CharField(choices=[('ZONA1', 'Zona 1'), ('ZONA2', 'Zona 2')], max_length=10)),
                ('note', models.CharField(blank=True, max_length=200)),
                ('active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['cliente_nombre'],
            },
        ),
    ]

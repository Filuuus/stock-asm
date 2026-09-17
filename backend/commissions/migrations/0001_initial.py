from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='CommissionCategoryRate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=20, unique=True)),
                ('label', models.CharField(max_length=60)),
                ('base_rate', models.DecimalField(decimal_places=4, max_digits=5)),
                ('decay_rate_per_week', models.DecimalField(decimal_places=4, default='0.0050', max_digits=5)),
                ('active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['code'],
            },
        ),
        migrations.CreateModel(
            name='ZeroCommissionProduct',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('producto_codigo', models.CharField(max_length=30, unique=True)),
                ('note', models.CharField(blank=True, max_length=200)),
                ('active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['producto_codigo'],
            },
        ),
    ]

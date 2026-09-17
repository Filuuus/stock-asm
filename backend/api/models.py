from django.db import models

class AdmProductos(models.Model):
    CIDPRODUCTO = models.AutoField(primary_key=True, db_column='CIDPRODUCTO')
    CCODIGOPRODUCTO = models.CharField(max_length=30, db_column='CCODIGOPRODUCTO')
    CNOMBREPRODUCTO = models.CharField(max_length=60, db_column='CNOMBREPRODUCTO')
    CPRECIO1 = models.FloatField(db_column='CPRECIO1')
    CTEXTOEXTRA1 = models.CharField(max_length=50, db_column='CTEXTOEXTRA1', null=True)
    # Classification slot 1 holds the product's supplier (used here as "brand").
    CIDVALORCLASIFICACION1 = models.IntegerField(db_column='CIDVALORCLASIFICACION1', null=True)

    class Meta:
        managed = False
        db_table = 'admProductos'


class AdmClasificacionesValores(models.Model):
    CIDVALORCLASIFICACION = models.AutoField(primary_key=True, db_column='CIDVALORCLASIFICACION')
    CVALORCLASIFICACION = models.CharField(max_length=60, db_column='CVALORCLASIFICACION')
    CIDCLASIFICACION = models.IntegerField(db_column='CIDCLASIFICACION')

    class Meta:
        managed = False
        db_table = 'admClasificacionesValores'


class AdmExistenciaCosto(models.Model):
    CIDPRODUCTO = models.ForeignKey(
        AdmProductos,
        primary_key=True,
        on_delete=models.DO_NOTHING,
        db_column='CIDPRODUCTO',
        related_name='existencias'
    )
    CENTRADASINICIALES = models.FloatField(db_column='CENTRADASINICIALES')
    CSALIDASINICIALES = models.FloatField(db_column='CSALIDASINICIALES')

    class Meta:
        managed = False
        db_table = 'admExistenciaCosto'

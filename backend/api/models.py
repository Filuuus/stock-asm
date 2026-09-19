from django.db import models

class AdmProductos(models.Model):
    CIDPRODUCTO = models.AutoField(primary_key=True, db_column='CIDPRODUCTO')
    CCODIGOPRODUCTO = models.CharField(max_length=30, db_column='CCODIGOPRODUCTO')
    CNOMBREPRODUCTO = models.CharField(max_length=60, db_column='CNOMBREPRODUCTO')
    CPRECIO1 = models.FloatField(db_column='CPRECIO1')
    CTEXTOEXTRA1 = models.CharField(max_length=50, db_column='CTEXTOEXTRA1', null=True)
    # Classification slot 1 holds the product's supplier (used here as "brand").
    CIDVALORCLASIFICACION1 = models.IntegerField(db_column='CIDVALORCLASIFICACION1', null=True)
    # Classification slot 2 holds a finer product-line description (e.g.
    # "DETERGENTES SURGE" vs "REFACCIONES VARIAS NACIONALES") - used to
    # detect the chemicals commission exception.
    CIDVALORCLASIFICACION2 = models.IntegerField(db_column='CIDVALORCLASIFICACION2', null=True)
    # 1 = physical product, 3 = service (confirmed against real data, 9 rows all year).
    CTIPOPRODUCTO = models.IntegerField(db_column='CTIPOPRODUCTO', null=True)

    class Meta:
        managed = False
        db_table = 'admProductos'


class AdmClientes(models.Model):
    CIDCLIENTEPROVEEDOR = models.AutoField(primary_key=True, db_column='CIDCLIENTEPROVEEDOR')
    CRAZONSOCIAL = models.CharField(max_length=200, db_column='CRAZONSOCIAL', null=True)

    class Meta:
        managed = False
        db_table = 'admClientes'


class AdmAgentes(models.Model):
    CIDAGENTE = models.AutoField(primary_key=True, db_column='CIDAGENTE')
    CCODIGOAGENTE = models.CharField(max_length=30, db_column='CCODIGOAGENTE')
    CNOMBREAGENTE = models.CharField(max_length=60, db_column='CNOMBREAGENTE')

    class Meta:
        managed = False
        db_table = 'admAgentes'


class AdmConceptos(models.Model):
    CIDCONCEPTODOCUMENTO = models.AutoField(primary_key=True, db_column='CIDCONCEPTODOCUMENTO')
    CPREFIJOCONCEPTO = models.CharField(max_length=10, db_column='CPREFIJOCONCEPTO', null=True)
    # The real tax series (A/B/blank=16%) - CPREFIJOCONCEPTO is always "F" for
    # display purposes regardless of series, this is the field that actually
    # varies.
    CSERIEPOROMISION = models.CharField(max_length=10, db_column='CSERIEPOROMISION', null=True)

    class Meta:
        managed = False
        db_table = 'admConceptos'


class AdmDocumentos(models.Model):
    CIDDOCUMENTO = models.AutoField(primary_key=True, db_column='CIDDOCUMENTO')
    CIDDOCUMENTODE = models.IntegerField(db_column='CIDDOCUMENTODE')
    CIDCONCEPTODOCUMENTO = models.IntegerField(db_column='CIDCONCEPTODOCUMENTO')
    CFOLIO = models.FloatField(db_column='CFOLIO')
    CFECHA = models.DateTimeField(db_column='CFECHA')
    CIDCLIENTEPROVEEDOR = models.IntegerField(db_column='CIDCLIENTEPROVEEDOR')
    CRAZONSOCIAL = models.CharField(max_length=200, db_column='CRAZONSOCIAL', null=True)
    CIDAGENTE = models.IntegerField(db_column='CIDAGENTE')
    CFECHAVENCIMIENTO = models.DateTimeField(db_column='CFECHAVENCIMIENTO', null=True)
    CPENDIENTE = models.FloatField(db_column='CPENDIENTE')
    CCANCELADO = models.IntegerField(db_column='CCANCELADO')
    CREFERENCIA = models.CharField(max_length=200, db_column='CREFERENCIA', null=True)
    CTOTAL = models.FloatField(db_column='CTOTAL', null=True)
    # Populated on Devolucion sobre Venta docs (points back at the Factura
    # being returned) but confirmed always 0 on Pago docs - not a general
    # payment-application link.
    CIDDOCUMENTOORIGEN = models.IntegerField(db_column='CIDDOCUMENTOORIGEN', null=True)

    class Meta:
        managed = False
        db_table = 'admDocumentos'


class AdmMovimientos(models.Model):
    CIDMOVIMIENTO = models.AutoField(primary_key=True, db_column='CIDMOVIMIENTO')
    CIDDOCUMENTO = models.IntegerField(db_column='CIDDOCUMENTO')
    CIDDOCUMENTODE = models.IntegerField(db_column='CIDDOCUMENTODE')
    CIDPRODUCTO = models.IntegerField(db_column='CIDPRODUCTO')
    CUNIDADES = models.FloatField(db_column='CUNIDADES')
    # CNETO is the line's amount BEFORE its own discount is applied - confirmed
    # against real data 2026-09-19 (CTOTAL = CNETO - discounts + tax exactly).
    # Never use CNETO alone as a commission base without subtracting these.
    CNETO = models.FloatField(db_column='CNETO')
    CDESCUENTO1 = models.FloatField(db_column='CDESCUENTO1', default=0)
    CDESCUENTO2 = models.FloatField(db_column='CDESCUENTO2', default=0)
    CDESCUENTO3 = models.FloatField(db_column='CDESCUENTO3', default=0)
    CDESCUENTO4 = models.FloatField(db_column='CDESCUENTO4', default=0)
    CDESCUENTO5 = models.FloatField(db_column='CDESCUENTO5', default=0)
    CTOTAL = models.FloatField(db_column='CTOTAL')

    class Meta:
        managed = False
        db_table = 'admMovimientos'


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

from django.conf import settings
from django.db import models


class ProductWeight(models.Model):
    """Kg per sale unit typed in by management for a product whose weight the app could only
    estimate. Wins over every automatic source (see weights.estimate_kg)."""
    # Not a real ForeignKey: mirrors AdmProductos.CIDPRODUCTO in the read-only ERP.
    producto_id = models.IntegerField(unique=True)
    kg = models.DecimalField(max_digits=9, decimal_places=3)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)


class ExcludedProduct(models.Model):
    """A product left out of Rentabilidad altogether, with its returns and credit notes: one-off
    deals that would distort the numbers (management, 2026-10-10: code 0001 "EQUIPO DE ORDEÑO
    COMPLETO", a complete milking system resold once)."""
    # Not a real ForeignKey: mirrors AdmProductos.CIDPRODUCTO in the read-only ERP.
    producto_id = models.IntegerField(unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


# Route costs (net result). Each cost lands in a pool, and each pool is spread over what it served:
# a route over its own zone's kg, the warehouse over every kg sold, the service crew over service
# sales. Agreed with management for the Bionat report (2026-10): kg as the key, PTU and office
# overhead left out.
POOL_CHOICES = [
    ('ZONA1', 'Zona 1'),
    ('ZONA2', 'Zona 2'),
    ('ALMACEN', 'Almacén (todas las ventas, por kg)'),
    ('SERVICIOS', 'Servicios (ventas de servicio)'),
]


class PoolEmployee(models.Model):
    """A payroll employee (Contpaqi Nóminas idempleado) whose pay goes to a pool. Bare id only:
    the name is looked up live, never stored (public repo)."""
    employee_id = models.IntegerField(unique=True)
    pool = models.CharField(max_length=10, choices=POOL_CHOICES)

    def __str__(self):
        return f'Empleado {self.employee_id} -> {self.pool}'


class PoolVehicle(models.Model):
    """A vehicle whose costs go to a pool. Fuel and maintenance come from the accountant's workbook
    for the months it covers; otherwise maintenance from its own ledger account and fuel from the
    ledger's GAS LP account (the one LP truck) or estimated from GPS km: km / km_per_liter *
    price_per_liter. Insurance is 1/12 of the yearly premium."""
    name = models.CharField(max_length=40)
    pool = models.CharField(max_length=10, choices=POOL_CHOICES)
    # Its name in the accountant's workbook, normalized ('HILUX1', 'MONTACARGAS'): months the workbook
    # covers take its fuel and maintenance from there instead of the ledger and GPS.
    sheet_name = models.CharField(max_length=40, blank=True)
    maintenance_account = models.CharField(max_length=20, blank=True, help_text='Cuenta contable, p. ej. 500511010')
    uses_lp = models.BooleanField(default=False, help_text='Su combustible es la cuenta GAS LP del libro')
    # Local only: IMEIs are kept out of the repo (see fleet/README.md).
    gps_imei = models.CharField(max_length=32, blank=True)
    km_per_liter = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    price_per_liter = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    annual_insurance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f'{self.name} -> {self.pool}'


class PoolMonthlyCost(models.Model):
    """A fixed monthly amount not in the ledger, e.g. the warehouse rent."""
    pool = models.CharField(max_length=10, choices=POOL_CHOICES)
    label = models.CharField(max_length=60)
    monthly_amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f'{self.label} -> {self.pool}'


class VehicleMonthlyCost(models.Model):
    """A vehicle's fuel or maintenance for one month, imported from the accountant's workbook
    (import_vehicle_reports). `vehicle` is the sheet's name normalized (vehicle_reports.vehicle_key)."""
    KIND_CHOICES = [('fuel', 'Combustible'), ('maintenance', 'Mantenimiento')]
    vehicle = models.CharField(max_length=40)
    month = models.CharField(max_length=7)  # 'YYYY-MM'
    kind = models.CharField(max_length=12, choices=KIND_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['vehicle', 'month', 'kind'], name='unique_vehicle_month_cost')]


class SavedPlace(models.Model):
    """A place saved in Google Maps by the sales team (import_maps_takeout), and the ERP client it is,
    when known. Names stay in the local database only: the repo is public."""
    url = models.CharField(max_length=500, unique=True)  # the place's Maps link; labeled places get a geo: key
    name = models.CharField(max_length=200)  # the list note when there is one (pins are named in it), else the title
    list_name = models.CharField(max_length=100)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    client_id = models.IntegerField(null=True, blank=True)  # admClientes.CIDCLIENTEPROVEEDOR
    matched_by = models.CharField(max_length=10, blank=True)  # 'auto' (name match) or 'manual'

    def __str__(self):
        return self.name

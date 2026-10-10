from django.contrib import admin

from .models import ExcludedProduct, PoolEmployee, PoolMonthlyCost, PoolVehicle, ProductWeight


@admin.register(PoolEmployee)
class PoolEmployeeAdmin(admin.ModelAdmin):
    list_display = ['employee_id', 'pool']
    list_editable = ['pool']


@admin.register(PoolVehicle)
class PoolVehicleAdmin(admin.ModelAdmin):
    list_display = ['name', 'pool', 'maintenance_account', 'uses_lp', 'km_per_liter', 'price_per_liter',
                    'annual_insurance', 'has_gps']
    list_editable = ['pool', 'maintenance_account', 'uses_lp', 'km_per_liter', 'price_per_liter', 'annual_insurance']

    @admin.display(boolean=True, description='GPS')
    def has_gps(self, obj):
        return bool(obj.gps_imei)


@admin.register(PoolMonthlyCost)
class PoolMonthlyCostAdmin(admin.ModelAdmin):
    list_display = ['label', 'pool', 'monthly_amount']
    list_editable = ['pool', 'monthly_amount']


admin.site.register(ProductWeight)
admin.site.register(ExcludedProduct)

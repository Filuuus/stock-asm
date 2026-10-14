from django.contrib import admin

from .models import ExcludedProduct, ExcludedSaleLine, PoolEmployee, PoolMonthlyCost, PoolVehicle, ProductWeight, SavedPlace


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
admin.site.register(ExcludedSaleLine)


@admin.register(SavedPlace)
class SavedPlaceAdmin(admin.ModelAdmin):
    """Fix a place's clients by hand (ERP client ids, e.g. [12, 40]); import_maps_takeout keeps manual matches."""
    list_display = ('name', 'list_name', 'client_ids', 'matched_by', 'lat', 'lng')
    list_editable = ('client_ids',)
    list_filter = ('matched_by', 'list_name')
    search_fields = ('name',)

    def save_model(self, request, obj, form, change):
        if 'client_ids' in form.changed_data:
            obj.matched_by = 'manual' if obj.client_ids else ''
        super().save_model(request, obj, form, change)

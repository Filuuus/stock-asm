from django.contrib import admin

from api.models import AdmClientes

from .models import CommissionCategoryRate, PuntoVentaClientZone, ZeroCommissionProduct


@admin.register(CommissionCategoryRate)
class CommissionCategoryRateAdmin(admin.ModelAdmin):
    list_display = ['code', 'label', 'base_rate', 'decay_rate_per_week', 'active']
    list_editable = ['base_rate', 'decay_rate_per_week', 'active']


@admin.register(ZeroCommissionProduct)
class ZeroCommissionProductAdmin(admin.ModelAdmin):
    list_display = ['producto_codigo', 'note', 'active']
    list_editable = ['note', 'active']


@admin.register(PuntoVentaClientZone)
class PuntoVentaClientZoneAdmin(admin.ModelAdmin):
    list_display = ['cliente_id', 'cliente_nombre', 'zone', 'note', 'active']
    list_editable = ['zone', 'note', 'active']
    search_fields = ['cliente_id']

    @admin.display(description='Cliente')
    def cliente_nombre(self, obj):
        # Looked up live from the ERP rather than stored here - see the
        # PuntoVentaClientZone docstring for why.
        return (
            AdmClientes.objects.filter(CIDCLIENTEPROVEEDOR=obj.cliente_id)
            .values_list('CRAZONSOCIAL', flat=True)
            .first()
            or '(no encontrado en ERP)'
        )

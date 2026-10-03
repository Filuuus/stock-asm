from django.contrib import admin

from api.models import AdmClientes

from .models import (
    CommissionCategoryRate, InvoiceCommissionOverride, LineRateOverride, PuntoVentaClientZone, ZeroCommissionProduct,
)


@admin.register(CommissionCategoryRate)
class CommissionCategoryRateAdmin(admin.ModelAdmin):
    list_display = ['code', 'label', 'base_rate', 'decay_rate_per_week', 'late_penalty', 'active']
    list_editable = ['base_rate', 'decay_rate_per_week', 'late_penalty', 'active']


@admin.register(ZeroCommissionProduct)
class ZeroCommissionProductAdmin(admin.ModelAdmin):
    list_display = ['producto_codigo', 'note', 'active']
    list_editable = ['note', 'active']


@admin.register(PuntoVentaClientZone)
class PuntoVentaClientZoneAdmin(admin.ModelAdmin):
    list_display = ['cliente_id', 'cliente_nombre', 'zone', 'product_codes', 'note', 'active']
    list_editable = ['zone', 'product_codes', 'note', 'active']
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


@admin.register(InvoiceCommissionOverride)
class InvoiceCommissionOverrideAdmin(admin.ModelAdmin):
    list_display = ['invoice_id', 'excluded', 'override_amount', 'zone', 'note', 'created_by', 'updated_at']
    list_editable = ['excluded', 'override_amount', 'zone', 'note']
    search_fields = ['invoice_id']
    readonly_fields = ['created_by', 'created_at', 'updated_at']


@admin.register(LineRateOverride)
class LineRateOverrideAdmin(admin.ModelAdmin):
    list_display = ['movimiento_id', 'invoice_id', 'rate', 'note', 'created_by', 'updated_at']
    list_editable = ['rate', 'note']
    search_fields = ['invoice_id', 'movimiento_id']
    readonly_fields = ['created_by', 'created_at', 'updated_at']

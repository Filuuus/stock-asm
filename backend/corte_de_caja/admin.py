from django.contrib import admin

from .models import CorteDeCajaAdjustment


@admin.register(CorteDeCajaAdjustment)
class CorteDeCajaAdjustmentAdmin(admin.ModelAdmin):
    list_display = ['invoice_id', 'event_date', 'payment_method', 'reviewed', 'excluded', 'note', 'created_by', 'updated_at']
    list_editable = ['payment_method', 'reviewed', 'excluded', 'note']
    search_fields = ['invoice_id']
    readonly_fields = ['created_by', 'created_at', 'updated_at', 'reviewed_by', 'reviewed_at']

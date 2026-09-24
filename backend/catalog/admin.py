from django.contrib import admin

from .models import ProductPriceVisibility


@admin.register(ProductPriceVisibility)
class ProductPriceVisibilityAdmin(admin.ModelAdmin):
    list_display = ['producto_codigo', 'public']
    list_editable = ['public']
    search_fields = ['producto_codigo']

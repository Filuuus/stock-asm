from django.contrib import admin

from .models import CommissionCategoryRate, ZeroCommissionProduct


@admin.register(CommissionCategoryRate)
class CommissionCategoryRateAdmin(admin.ModelAdmin):
    list_display = ['code', 'label', 'base_rate', 'decay_rate_per_week', 'active']
    list_editable = ['base_rate', 'decay_rate_per_week', 'active']


@admin.register(ZeroCommissionProduct)
class ZeroCommissionProductAdmin(admin.ModelAdmin):
    list_display = ['producto_codigo', 'note', 'active']
    list_editable = ['note', 'active']

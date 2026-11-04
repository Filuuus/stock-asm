from django.contrib import admin

from .models import OrderLine, Parlor, ParlorPart, Visit


class ParlorPartInline(admin.TabularInline):
    model = ParlorPart
    extra = 1


@admin.register(Parlor)
class ParlorAdmin(admin.ModelAdmin):
    list_display = ('client_code', 'label', 'stalls', 'cows', 'milking_hours_per_day', 'active')
    inlines = [ParlorPartInline]


admin.site.register(Visit)
admin.site.register(OrderLine)

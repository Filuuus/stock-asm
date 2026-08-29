from django.contrib import admin
from .models import Product, StockMovement

admin.site.register(Product)
admin.site.register(StockMovement)
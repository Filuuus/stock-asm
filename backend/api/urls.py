from django.urls import path
from .views import inventory_list

urlpatterns = [
    path('inventory/', inventory_list, name='inventory-list'),
]

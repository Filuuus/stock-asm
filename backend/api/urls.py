from django.urls import path
from .views import inventory_list, product_detail

urlpatterns = [
    path('inventory/', inventory_list, name='inventory-list'),
    path('inventory/<str:code>/', product_detail, name='product-detail'),
]

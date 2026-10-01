from django.urls import path
from .views import gea_parts, inventory_list, product_detail

urlpatterns = [
    path('inventory/', inventory_list, name='inventory-list'),
    path('gea-parts/', gea_parts, name='gea-parts'),
    path('inventory/<str:code>/', product_detail, name='product-detail'),
]

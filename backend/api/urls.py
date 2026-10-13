from django.urls import path
from .views import gea_parts, inventory_list, product_description, product_detail, product_photo, product_photos

urlpatterns = [
    path('inventory/', inventory_list, name='inventory-list'),
    path('gea-parts/', gea_parts, name='gea-parts'),
    path('inventory/<str:key>/', product_detail, name='product-detail'),
    path('inventory/<str:key>/fotos/', product_photos, name='product-photos'),
    path('inventory/<str:key>/fotos/<int:pk>/', product_photo, name='product-photo'),
    path('inventory/<str:key>/descripcion/', product_description, name='product-description'),
]

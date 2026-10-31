from django.urls import path
from catalog.views import rules_brand, rules_category, rules_hidden, rules_overview, rules_special, rules_specials

from .views import gea_parts, inventory_list, product_description, product_detail, product_photo, product_photos

urlpatterns = [
    path('catalogo/ajustes/', rules_overview, name='catalog-rules'),
    path('catalogo/ajustes/especiales/', rules_specials, name='catalog-rules-specials'),
    path('catalogo/ajustes/especiales/<int:key>/', rules_special, name='catalog-rules-special'),
    path('catalogo/ajustes/ocultos/<int:key>/', rules_hidden, name='catalog-rules-hidden'),
    path('catalogo/ajustes/categorias/<str:category>/', rules_category, name='catalog-rules-category'),
    path('catalogo/ajustes/marcas/', rules_brand, name='catalog-rules-brand'),
    path('inventory/', inventory_list, name='inventory-list'),
    path('gea-parts/', gea_parts, name='gea-parts'),
    path('inventory/<str:key>/', product_detail, name='product-detail'),
    path('inventory/<str:key>/fotos/', product_photos, name='product-photos'),
    path('inventory/<str:key>/fotos/<int:pk>/', product_photo, name='product-photo'),
    path('inventory/<str:key>/descripcion/', product_description, name='product-description'),
]

from django.urls import path

from .views import invoice_detail_view, invoice_search

urlpatterns = [
    path('buscar/', invoice_search, name='facturas-search'),
    path('<int:invoice_id>/', invoice_detail_view, name='facturas-detail'),
]

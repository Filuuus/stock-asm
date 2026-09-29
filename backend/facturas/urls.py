from django.urls import path

from .views import client_history_view, invoice_detail_view, invoice_search

urlpatterns = [
    path('buscar/', invoice_search, name='facturas-search'),
    path('<int:invoice_id>/', invoice_detail_view, name='facturas-detail'),
    path('clientes/<int:client_id>/', client_history_view, name='facturas-client-history'),
]

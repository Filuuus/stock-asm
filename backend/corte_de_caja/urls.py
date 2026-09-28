from django.urls import path

from .views import adjustment_delete, adjustment_upsert, confirm_suggestions, corte_de_caja_summary

urlpatterns = [
    path('summary/', corte_de_caja_summary, name='corte-de-caja-summary'),
    path('confirm-suggestions/', confirm_suggestions, name='corte-de-caja-confirm-suggestions'),
    path('adjustments/', adjustment_upsert, name='corte-de-caja-adjustment-upsert'),
    path('adjustments/<int:invoice_id>/<str:event_date>/', adjustment_delete, name='corte-de-caja-adjustment-delete'),
]

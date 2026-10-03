from django.urls import path

from .views import (
    commissions_summary, invoice_search, line_rate_delete, line_rate_save, override_create, override_delete,
)

urlpatterns = [
    path('summary/', commissions_summary, name='commissions-summary'),
    path('invoices/search/', invoice_search, name='commissions-invoice-search'),
    path('overrides/', override_create, name='commissions-override-create'),
    path('overrides/<int:invoice_id>/', override_delete, name='commissions-override-delete'),
    path('line-rates/', line_rate_save, name='commissions-line-rate-save'),
    path('line-rates/<int:movimiento_id>/', line_rate_delete, name='commissions-line-rate-delete'),
]

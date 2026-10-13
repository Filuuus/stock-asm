from django.urls import path

from .views import invoices, profitability, set_exclusion, set_line_exclusion, set_weight, setup

urlpatterns = [
    path('', profitability, name='profitability'),
    path('setup/', setup, name='profitability-setup'),
    path('invoices/', invoices, name='profitability-invoices'),
    path('weights/', set_weight, name='profitability-weights'),
    path('exclusions/', set_exclusion, name='profitability-exclusions'),
    path('excluded-lines/', set_line_exclusion, name='profitability-excluded-lines'),
]

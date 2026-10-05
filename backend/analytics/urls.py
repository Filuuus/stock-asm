from django.urls import path

from .views import overdue_clients_list, sales_summary

urlpatterns = [
    path('sales/', sales_summary, name='analytics-sales'),
    path('overdue-clients/', overdue_clients_list, name='analytics-overdue-clients'),
]

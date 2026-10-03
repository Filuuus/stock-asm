from django.urls import path

from .views import sales_summary

urlpatterns = [
    path('sales/', sales_summary, name='analytics-sales'),
]

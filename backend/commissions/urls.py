from django.urls import path

from .views import commissions_summary

urlpatterns = [
    path('summary/', commissions_summary, name='commissions-summary'),
]

from django.urls import path

from .views import profitability, set_weight

urlpatterns = [
    path('', profitability, name='profitability'),
    path('weights/', set_weight, name='profitability-weights'),
]

from django.urls import path

from .views import quote_decide, quote_public, quote_requests, quote_staff

urlpatterns = [
    path('', quote_requests, name='quote-requests'),
    path('publica/<str:token>/', quote_public, name='quote-public'),
    path('<int:pk>/', quote_staff, name='quote-staff'),
    path('<int:pk>/<str:decision>/', quote_decide, name='quote-decide'),
]

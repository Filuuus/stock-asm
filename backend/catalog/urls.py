from django.urls import path

from .views import quote_accept, quote_action, quote_note, quote_pending, quote_public, quote_requests, quote_staff

urlpatterns = [
    path('', quote_requests, name='quote-requests'),
    path('pendientes/', quote_pending, name='quote-pending'),
    path('publica/<str:token>/', quote_public, name='quote-public'),
    path('publica/<str:token>/aprobar/', quote_accept, name='quote-accept'),
    path('<int:pk>/', quote_staff, name='quote-staff'),
    path('<int:pk>/notas/<int:note>/', quote_note, name='quote-note'),
    path('<int:pk>/<str:action>/', quote_action, name='quote-action'),
]

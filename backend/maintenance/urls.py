from django.urls import path

from .views import external_change, external_changes, part, plan, quote

urlpatterns = [
    path('plan/', plan, name='service-plan'),
    path('salas/<int:pk>/cotizar/', quote, name='service-quote'),
    path('piezas/<int:pk>/', part, name='service-part'),
    path('externos/', external_changes, name='service-external-changes'),
    path('externos/<int:pk>/', external_change, name='service-external-change'),
]

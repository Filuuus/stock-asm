from django.urls import path

from .views import orders, plan, receive_order_line, update_visit

urlpatterns = [
    path('plan/', plan, name='service-plan'),
    path('visitas/<int:pk>/', update_visit, name='service-visit'),
    path('pedidos/', orders, name='service-orders'),
    path('pedidos/<int:pk>/', receive_order_line, name='service-order-line'),
]

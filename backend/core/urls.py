from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/', include('api.urls')),
    path('api/commissions/', include('commissions.urls')),
    path('api/corte-de-caja/', include('corte_de_caja.urls')),
]

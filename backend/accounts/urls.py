from django.urls import path

from .views import audit_log, login_view, logout_view, me, user_detail, users_list

urlpatterns = [
    path('me/', me, name='auth-me'),
    path('login/', login_view, name='auth-login'),
    path('logout/', logout_view, name='auth-logout'),
    path('users/', users_list, name='auth-users'),
    path('users/<int:user_id>/', user_detail, name='auth-user-detail'),
    path('audit-log/', audit_log, name='auth-audit-log'),
]

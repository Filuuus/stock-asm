from rest_framework.permissions import BasePermission

from .models import Profile


def is_management(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.role == Profile.ROLE_MANAGEMENT)


def is_accounting(user):
    if not user or not user.is_authenticated:
        return False
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.role == Profile.ROLE_ACCOUNTING)


class IsWorker(BasePermission):
    """Any logged-in account - salesperson, accounting, or management. All
    accounts are workers (no customer accounts exist yet), so this is just
    "is logged in".
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class IsManagement(BasePermission):
    def has_permission(self, request, view):
        return is_management(request.user)


class IsAccountingOrManagement(BasePermission):
    """Corte de Caja is an office/accounting tool, not something salespeople
    need (see the corte-de-caja-dashboard project memory - both of its real
    users are office staff, neither is a Vendedor) - gated more narrowly
    than the general IsWorker check used by Comisiones.
    """

    def has_permission(self, request, view):
        user = request.user
        return is_accounting(user) or is_management(user)

from rest_framework.permissions import BasePermission

from .models import Profile


def is_management(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.role == Profile.ROLE_MANAGEMENT)


class IsWorker(BasePermission):
    """Any logged-in account - salesperson or management. All accounts are
    workers (no customer accounts exist yet), so this is just "is logged in".
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class IsManagement(BasePermission):
    def has_permission(self, request, view):
        return is_management(request.user)

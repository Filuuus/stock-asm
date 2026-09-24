from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import AccountAuditLogEntry, Profile
from .permissions import IsManagement, is_management


def _user_payload(user):
    profile = getattr(user, 'profile', None)
    role = Profile.ROLE_MANAGEMENT if is_management(user) else (profile.role if profile else Profile.ROLE_SALESPERSON)
    return {
        'authenticated': True,
        'username': user.username,
        'role': role,
    }


@ensure_csrf_cookie
@api_view(['GET'])
@permission_classes([AllowAny])
def me(request):
    if not request.user.is_authenticated:
        return Response({'authenticated': False})
    return Response(_user_payload(request.user))


# Brute-force protection on login. Keyed by IP (not username) so an
# attacker can't just cycle usernames to dodge the limit - real client and
# payroll data sits behind this login now, not just a demo. Uses the
# existing Redis cache (already relied on by api.services.get_inventory_catalog)
# rather than adding a new dependency like django-ratelimit, matching this
# project's "lightweight additions" preference.
LOGIN_RATE_LIMIT_ATTEMPTS = 5
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 15 * 60


def _client_ip(request):
    # No reverse proxy in front of this yet (see project memory on
    # deployment) - REMOTE_ADDR is the real client IP for now. Would need
    # to read X-Forwarded-For instead if that changes.
    return request.META.get('REMOTE_ADDR', 'unknown')


def _login_attempts_key(request):
    return f'login_attempts:{_client_ip(request)}'


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    attempts_key = _login_attempts_key(request)
    if cache.get(attempts_key, 0) >= LOGIN_RATE_LIMIT_ATTEMPTS:
        return Response(
            {'error': 'Demasiados intentos fallidos. Intente de nuevo en unos minutos.'},
            status=429,
        )

    username = request.data.get('username', '')
    password = request.data.get('password', '')
    user = authenticate(request, username=username, password=password)
    if user is None:
        cache.set(attempts_key, cache.get(attempts_key, 0) + 1, LOGIN_RATE_LIMIT_WINDOW_SECONDS)
        return Response({'error': 'Usuario o contraseña incorrectos.'}, status=400)

    cache.delete(attempts_key)
    auth_login(request, user)
    return Response(_user_payload(user))


@api_view(['POST'])
@permission_classes([AllowAny])
def logout_view(request):
    auth_logout(request)
    return Response({'authenticated': False})


# Self-service account management for management users, so creating a
# worker account/resetting a password no longer depends on someone using
# the Django admin (requested 2026-09-24). Deliberately does not expose
# is_staff/is_superuser - this panel only ever manages the app's own
# Profile.role and basic account lifecycle, never Django-admin permissions.

_PASSWORD_ERROR_MESSAGES = {
    'password_too_short': 'La contraseña debe tener al menos 8 caracteres.',
    'password_too_common': 'Esa contraseña es demasiado común, elija otra.',
    'password_entirely_numeric': 'La contraseña no puede ser solo números.',
    'password_too_similar': 'La contraseña se parece demasiado al usuario.',
}


def _validate_password(password, username):
    if not password:
        return 'La contraseña es requerida.'
    try:
        validate_password(password, User(username=username))
    except DjangoValidationError as exc:
        messages = [
            _PASSWORD_ERROR_MESSAGES.get(getattr(err, 'code', None), err.messages[0])
            for err in exc.error_list
        ]
        return ' '.join(dict.fromkeys(messages))
    return None


def _user_admin_payload(user):
    return {
        'id': user.id,
        'username': user.username,
        'role': user.profile.role,
        'zone': user.profile.zone,
        'is_active': user.is_active,
        'date_joined': user.date_joined,
        'last_login': user.last_login,
    }


def _log_account_action(actor, target_username, action, detail=''):
    AccountAuditLogEntry.objects.create(
        actor_username=actor.username,
        target_username=target_username,
        action=action,
        detail=detail,
    )


@api_view(['GET', 'POST'])
@permission_classes([IsManagement])
def users_list(request):
    if request.method == 'GET':
        users = User.objects.select_related('profile').order_by('username')
        return Response([_user_admin_payload(u) for u in users])

    username = (request.data.get('username') or '').strip()
    password = request.data.get('password') or ''
    role = request.data.get('role') or Profile.ROLE_SALESPERSON
    zone = request.data.get('zone') or ''

    if not username:
        return Response({'error': 'El usuario es requerido.'}, status=400)
    if role not in dict(Profile.ROLE_CHOICES):
        return Response({'error': 'Rol inválido.'}, status=400)
    if zone and zone not in dict(Profile.ZONE_CHOICES):
        return Response({'error': 'Zona inválida.'}, status=400)
    if User.objects.filter(username=username).exists():
        return Response({'error': 'Ese nombre de usuario ya existe.'}, status=400)

    password_error = _validate_password(password, username)
    if password_error:
        return Response({'error': password_error}, status=400)

    user = User.objects.create_user(username=username, password=password)
    user.profile.role = role
    user.profile.zone = zone
    user.profile.save()
    _log_account_action(request.user, username, AccountAuditLogEntry.ACTION_CREATED, detail=dict(Profile.ROLE_CHOICES)[role])
    return Response(_user_admin_payload(user), status=201)


@api_view(['PATCH'])
@permission_classes([IsManagement])
def user_detail(request, user_id):
    try:
        user = User.objects.select_related('profile').get(pk=user_id)
    except User.DoesNotExist:
        return Response({'error': 'Usuario no encontrado.'}, status=404)

    is_self = user.id == request.user.id
    data = request.data

    if 'role' in data:
        role = data['role']
        if role not in dict(Profile.ROLE_CHOICES):
            return Response({'error': 'Rol inválido.'}, status=400)
        if is_self and role != user.profile.role:
            return Response({'error': 'No puede cambiar su propio rol.'}, status=400)
        if role != user.profile.role:
            role_labels = dict(Profile.ROLE_CHOICES)
            _log_account_action(
                request.user, user.username, AccountAuditLogEntry.ACTION_ROLE_CHANGED,
                detail=f'{role_labels[user.profile.role]} -> {role_labels[role]}',
            )
            user.profile.role = role
            user.profile.save()

    if 'zone' in data:
        zone = data['zone'] or ''
        if zone and zone not in dict(Profile.ZONE_CHOICES):
            return Response({'error': 'Zona inválida.'}, status=400)
        if zone != user.profile.zone:
            zone_labels = dict(Profile.ZONE_CHOICES)
            _log_account_action(
                request.user, user.username, AccountAuditLogEntry.ACTION_ZONE_CHANGED,
                detail=f'{zone_labels.get(user.profile.zone, "Sin zona")} -> {zone_labels.get(zone, "Sin zona")}',
            )
            user.profile.zone = zone
            user.profile.save()

    if 'is_active' in data:
        is_active_value = bool(data['is_active'])
        if is_self and not is_active_value:
            return Response({'error': 'No puede desactivar su propia cuenta.'}, status=400)
        if is_active_value != user.is_active:
            _log_account_action(
                request.user, user.username,
                AccountAuditLogEntry.ACTION_ACTIVATED if is_active_value else AccountAuditLogEntry.ACTION_DEACTIVATED,
            )
            user.is_active = is_active_value
            user.save(update_fields=['is_active'])

    if data.get('password'):
        password_error = _validate_password(data['password'], user.username)
        if password_error:
            return Response({'error': password_error}, status=400)
        user.set_password(data['password'])
        user.save(update_fields=['password'])
        _log_account_action(request.user, user.username, AccountAuditLogEntry.ACTION_PASSWORD_RESET)

    user.refresh_from_db()
    return Response(_user_admin_payload(user))


@api_view(['GET'])
@permission_classes([IsManagement])
def audit_log(request):
    entries = AccountAuditLogEntry.objects.all()[:100]
    return Response([
        {
            'id': e.id,
            'actor_username': e.actor_username,
            'target_username': e.target_username,
            'action': e.action,
            'detail': e.detail,
            'created_at': e.created_at,
        }
        for e in entries
    ])

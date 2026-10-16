"""Login, its brute-force limit, CSRF on session requests, roles and the /usuarios panel.
Local database only (databases = {'default'}); every test gets a fresh in-memory cache so
login attempts never count against the dev Redis or leak between tests."""
from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser, User
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from .models import AccountAuditLogEntry, Profile
from .permissions import IsAccountingOrManagement, IsManagement, IsWorker
from .views import LOGIN_RATE_LIMIT_ATTEMPTS

PASSWORD = 'pasto-verde-2026'
LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


def make_user(username, role=Profile.ROLE_SALESPERSON, **extra):
    user = User.objects.create_user(username=username, password=PASSWORD, **extra)
    user.profile.role = role
    user.profile.save()
    return user


@override_settings(CACHES=LOCMEM)
class LoginTests(TestCase):
    databases = {'default'}

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        make_user('vendedor')

    def login(self, password=PASSWORD, ip='10.0.0.1', username='vendedor'):
        return self.client.post('/api/auth/login/', {'username': username, 'password': password},
                                format='json', REMOTE_ADDR=ip)

    def test_good_password_logs_in_and_returns_role(self):
        res = self.login()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {'authenticated': True, 'username': 'vendedor', 'role': Profile.ROLE_SALESPERSON})
        self.assertEqual(self.client.get('/api/auth/me/').json()['username'], 'vendedor')

    def test_wrong_password_is_rejected(self):
        res = self.login(password='otra-cosa')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.client.get('/api/auth/me/').json(), {'authenticated': False})

    def test_inactive_account_cannot_log_in(self):
        make_user('baja', is_active=False)
        self.assertEqual(self.login(username='baja').status_code, 400)

    def test_logout_ends_the_session(self):
        self.login()
        self.client.post('/api/auth/logout/')
        self.assertEqual(self.client.get('/api/auth/me/').json(), {'authenticated': False})

    def test_me_sets_the_csrf_cookie(self):
        # The frontend reads csrftoken from here before its first mutating request.
        self.assertIn('csrftoken', self.client.get('/api/auth/me/').cookies)

    def test_superuser_counts_as_management(self):
        User.objects.create_superuser(username='admin', password=PASSWORD)
        self.assertEqual(self.login(username='admin').json()['role'], Profile.ROLE_MANAGEMENT)


@override_settings(CACHES=LOCMEM)
class LoginRateLimitTests(TestCase):
    databases = {'default'}

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        make_user('vendedor')

    def login(self, password, ip='10.0.0.1'):
        return self.client.post('/api/auth/login/', {'username': 'vendedor', 'password': password},
                                format='json', REMOTE_ADDR=ip)

    def fail(self, times, ip='10.0.0.1'):
        for _ in range(times):
            self.assertEqual(self.login('mal', ip).status_code, 400)

    def test_locked_out_after_the_limit_even_with_the_right_password(self):
        self.fail(LOGIN_RATE_LIMIT_ATTEMPTS)
        self.assertEqual(self.login('mal').status_code, 429)
        self.assertEqual(self.login(PASSWORD).status_code, 429)

    def test_one_attempt_below_the_limit_still_lets_the_right_password_in(self):
        self.fail(LOGIN_RATE_LIMIT_ATTEMPTS - 1)
        self.assertEqual(self.login(PASSWORD).status_code, 200)

    def test_a_successful_login_resets_the_count(self):
        self.fail(LOGIN_RATE_LIMIT_ATTEMPTS - 1)
        self.login(PASSWORD)
        self.client.post('/api/auth/logout/')
        self.fail(LOGIN_RATE_LIMIT_ATTEMPTS - 1)
        self.assertEqual(self.login(PASSWORD).status_code, 200)

    def test_counted_per_ip_not_per_username(self):
        self.fail(LOGIN_RATE_LIMIT_ATTEMPTS, ip='10.0.0.1')
        self.assertEqual(self.login(PASSWORD, ip='10.0.0.2').status_code, 200)
        # Switching usernames from the blocked address doesn't help.
        make_user('otro')
        res = self.client.post('/api/auth/login/', {'username': 'otro', 'password': PASSWORD},
                               format='json', REMOTE_ADDR='10.0.0.1')
        self.assertEqual(res.status_code, 429)


@override_settings(CACHES=LOCMEM)
class CsrfTests(TestCase):
    """A logged-in session's mutating requests need the CSRF token (DRF's SessionAuthentication)."""
    databases = {'default'}

    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)
        self.boss = make_user('gerente', Profile.ROLE_MANAGEMENT)
        self.worker = make_user('vendedor')
        self.client.force_login(self.boss)
        self.token = self.client.get('/api/auth/me/').cookies['csrftoken'].value

    def test_mutating_request_without_token_is_rejected(self):
        res = self.client.patch(f'/api/auth/users/{self.worker.id}/', {'zone': 'ZONA1'}, format='json')
        self.assertEqual(res.status_code, 403)
        self.worker.profile.refresh_from_db()
        self.assertEqual(self.worker.profile.zone, '')

    def test_mutating_request_with_token_goes_through(self):
        res = self.client.patch(f'/api/auth/users/{self.worker.id}/', {'zone': 'ZONA1'}, format='json',
                                HTTP_X_CSRFTOKEN=self.token)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['zone'], 'ZONA1')

    def test_wrong_token_is_rejected(self):
        res = self.client.patch(f'/api/auth/users/{self.worker.id}/', {'zone': 'ZONA1'}, format='json',
                                HTTP_X_CSRFTOKEN='x' * 32)
        self.assertEqual(res.status_code, 403)

    def test_cross_site_logout_is_rejected(self):
        self.assertEqual(self.client.post('/api/auth/logout/').status_code, 403)
        self.assertTrue(self.client.get('/api/auth/me/').json()['authenticated'])

    def test_reads_do_not_need_the_token(self):
        self.assertEqual(self.client.get('/api/auth/users/').status_code, 200)


class RolePermissionTests(SimpleTestCase):
    """The three gates every other app uses, checked on each kind of account."""

    def user(self, role=None, superuser=False):
        profile = SimpleNamespace(role=role) if role else None
        return SimpleNamespace(is_authenticated=True, is_superuser=superuser, profile=profile)

    def allowed(self, permission, user):
        return permission().has_permission(SimpleNamespace(user=user), None)

    def test_matrix(self):
        accounts = {
            'anonymous': AnonymousUser(),
            'salesperson': self.user(Profile.ROLE_SALESPERSON),
            'accounting': self.user(Profile.ROLE_ACCOUNTING),
            'management': self.user(Profile.ROLE_MANAGEMENT),
            'superuser': self.user(Profile.ROLE_SALESPERSON, superuser=True),
            'no profile': self.user(),
        }
        expected = {  # IsWorker, IsAccountingOrManagement, IsManagement
            'anonymous': (False, False, False),
            'salesperson': (True, False, False),
            'accounting': (True, True, False),
            'management': (True, True, True),
            'superuser': (True, True, True),
            'no profile': (True, False, False),
        }
        for name, user in accounts.items():
            with self.subTest(name):
                got = tuple(self.allowed(p, user) for p in (IsWorker, IsAccountingOrManagement, IsManagement))
                self.assertEqual(got, expected[name])


@override_settings(CACHES=LOCMEM)
class UserAdminTests(TestCase):
    """/usuarios: management only, can't lock itself out, and every change is logged."""
    databases = {'default'}

    def setUp(self):
        self.client = APIClient()
        self.boss = make_user('gerente', Profile.ROLE_MANAGEMENT)
        self.worker = make_user('vendedor')

    def as_user(self, user):
        self.client.force_login(user)

    def test_only_management_reaches_the_panel(self):
        for role in (Profile.ROLE_SALESPERSON, Profile.ROLE_ACCOUNTING):
            with self.subTest(role):
                self.as_user(make_user(f'u-{role}', role))
                self.assertEqual(self.client.get('/api/auth/users/').status_code, 403)
                self.assertEqual(self.client.get('/api/auth/audit-log/').status_code, 403)
                res = self.client.patch(f'/api/auth/users/{self.worker.id}/', {'role': Profile.ROLE_MANAGEMENT},
                                        format='json')
                self.assertEqual(res.status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get('/api/auth/users/').status_code, 403)
        self.worker.profile.refresh_from_db()
        self.assertEqual(self.worker.profile.role, Profile.ROLE_SALESPERSON)

    def test_create_user_defaults_to_salesperson_and_is_logged(self):
        self.as_user(self.boss)
        res = self.client.post('/api/auth/users/', {'username': 'nuevo', 'password': PASSWORD}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()['role'], Profile.ROLE_SALESPERSON)
        entry = AccountAuditLogEntry.objects.get()
        self.assertEqual((entry.actor_username, entry.target_username, entry.action),
                         ('gerente', 'nuevo', AccountAuditLogEntry.ACTION_CREATED))

    def test_create_user_rejects_bad_input(self):
        self.as_user(self.boss)
        cases = {
            'weak password': {'username': 'nuevo', 'password': '12345678'},
            'duplicate': {'username': 'vendedor', 'password': PASSWORD},
            'bad role': {'username': 'nuevo', 'password': PASSWORD, 'role': 'ADMIN'},
            'bad zone': {'username': 'nuevo', 'password': PASSWORD, 'zone': 'ZONA9'},
            'no username': {'username': ' ', 'password': PASSWORD},
        }
        for name, body in cases.items():
            with self.subTest(name):
                self.assertEqual(self.client.post('/api/auth/users/', body, format='json').status_code, 400)
        self.assertFalse(User.objects.filter(username='nuevo').exists())

    def test_management_cannot_demote_or_deactivate_itself(self):
        self.as_user(self.boss)
        url = f'/api/auth/users/{self.boss.id}/'
        self.assertEqual(self.client.patch(url, {'role': Profile.ROLE_SALESPERSON}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'is_active': False}, format='json').status_code, 400)
        self.boss.refresh_from_db()
        self.assertTrue(self.boss.is_active)
        self.assertEqual(self.boss.profile.role, Profile.ROLE_MANAGEMENT)

    def test_role_change_deactivation_and_password_reset_are_logged(self):
        self.as_user(self.boss)
        url = f'/api/auth/users/{self.worker.id}/'
        self.client.patch(url, {'role': Profile.ROLE_ACCOUNTING}, format='json')
        self.client.patch(url, {'is_active': False}, format='json')
        self.client.patch(url, {'password': 'otra-clave-segura-1'}, format='json')
        actions = set(AccountAuditLogEntry.objects.values_list('action', flat=True))
        self.assertEqual(actions, {AccountAuditLogEntry.ACTION_ROLE_CHANGED, AccountAuditLogEntry.ACTION_DEACTIVATED,
                                   AccountAuditLogEntry.ACTION_PASSWORD_RESET})
        self.worker.refresh_from_db()
        self.assertFalse(self.worker.is_active)
        self.assertTrue(self.worker.check_password('otra-clave-segura-1'))

    def test_password_reset_is_validated(self):
        self.as_user(self.boss)
        res = self.client.patch(f'/api/auth/users/{self.worker.id}/', {'password': 'vendedor'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.check_password(PASSWORD))

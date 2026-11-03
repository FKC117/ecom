from datetime import timedelta

from axes.models import AccessAttempt
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone
from import_export.admin import ImportExportModelAdmin


class LoginProtectionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('login-buyer', password='test-password-182!')

    def fail_login(self, path='/api/account/login/', **extra):
        return self.client.post(path, {'username': self.user.username, 'password': 'wrong'}, **extra)

    def test_shared_routes_lockout_and_unlock(self):
        for path in ['/api/account/login/', '/api/control/login/', '/admin/login/', '/api/account/login/']:
            self.fail_login(path)
        result = self.fail_login()
        self.assertEqual(result.status_code, 429)
        self.assertEqual(result['Retry-After'], '900')
        self.assertIn('error', result.json())
        self.assertEqual(self.client.post('/api/account/login/', {'username': self.user.username, 'password': 'test-password-182!'}).status_code, 429)
        self.assertEqual(self.fail_login('/admin/login/').status_code, 429)
        # The same deletion used by permission-checked admin controls unlocks the pair.
        AccessAttempt.objects.all().delete()
        self.assertEqual(self.client.post('/api/account/login/', {'username': self.user.username, 'password': 'test-password-182!'}).status_code, 200)

    def test_cooloff_success_reset_and_shared_ip(self):
        for _ in range(5):
            self.fail_login()
        other = get_user_model().objects.create_user('other-buyer', password='test-password-182!')
        self.assertEqual(self.client.post('/api/account/login/', {'username': other.username, 'password': 'test-password-182!'}).status_code, 200)
        self.client.logout()
        AccessAttempt.objects.update(attempt_time=timezone.now() - timedelta(minutes=16))
        self.assertEqual(self.client.post('/api/account/login/', {'username': self.user.username, 'password': 'test-password-182!'}).status_code, 200)
        self.assertFalse(AccessAttempt.objects.filter(username=self.user.username).exists())

    def test_trusted_ip_and_permissions(self):
        self.fail_login(HTTP_X_FORWARDED_FOR='198.51.100.25')
        self.assertEqual(AccessAttempt.objects.get().ip_address, '127.0.0.1')
        self.assertNotIn('wrong', AccessAttempt.objects.get().post_data)
        with self.settings(COMMERCE_TRUSTED_PROXIES=['127.0.0.1/32']):
            self.fail_login(HTTP_X_FORWARDED_FOR='198.51.100.25')
        self.assertTrue(AccessAttempt.objects.filter(ip_address='198.51.100.25').exists())
        staff = get_user_model().objects.create_user('security-staff', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get('/api/control/models/axes/accessattempt/').status_code, 403)
        root = get_user_model().objects.create_superuser('security-root', password='test-password-182!')
        self.client.force_login(root)
        self.assertEqual(self.client.get('/api/control/models/axes/accessattempt/').status_code, 200)
        self.assertIsInstance(admin.site._registry[AccessAttempt], ImportExportModelAdmin)
        self.assertEqual(self.client.post('/api/control/models/axes/accessattempt/new/', {}).status_code, 403)
        attempt = AccessAttempt.objects.first()
        detail = self.client.get(f'/api/control/models/axes/accessattempt/{attempt.pk}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(self.client.post(f'/api/control/models/axes/accessattempt/{attempt.pk}/delete/', {'confirm': 'yes'}).status_code, 200)
        self.assertFalse(AccessAttempt.objects.filter(pk=attempt.pk).exists())

    def test_csrf_still_required(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/api/account/login/', {'username': self.user.username, 'password': 'wrong'}).status_code, 403)
        self.assertFalse(AccessAttempt.objects.exists())

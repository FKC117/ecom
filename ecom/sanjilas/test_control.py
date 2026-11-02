import io
import tempfile
from unittest.mock import patch

from PIL import Image
from django.contrib import admin
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import include, path
from import_export.admin import ImportExportModelAdmin

from .models import Category, Product, SiteSettings


ROOT = '/api/control/'
COLLECTIONS = ROOT + 'models/sanjilas/category/'
PRODUCTS = ROOT + 'models/sanjilas/product/'


class ControlTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_superuser('owner', 'owner@example.com', 'Owner-test-password1')
        cls.staff = get_user_model().objects.create_user('editor', password='Editor-test-password1', is_staff=True)
        cls.customer = get_user_model().objects.create_user('customer', password='Customer-test-password1')
        cls.category = Category.objects.create(name='Rings', slug='rings')
        cls.product = Product.objects.create(name='Ring', slug='ring', category=cls.category)
        SiteSettings.objects.create()

    def setUp(self):
        cache.clear()

    def grant(self, *codenames):
        role = Group.objects.create(name='Content team')
        role.permissions.set(Permission.objects.filter(content_type__app_label='sanjilas', codename__in=codenames))
        self.staff.groups.add(role)
        self.client.force_login(self.staff)

    def test_shared_login_routes_roles_without_granting_control_access(self):
        for username, password, destination in [
            ('customer', 'Customer-test-password1', '/account/'),
            ('editor', 'Editor-test-password1', '/control/'),
            ('owner', 'Owner-test-password1', '/control/'),
        ]:
            self.client.logout()
            response = self.client.post('/api/account/login/', {'username': username, 'password': password})
            self.assertEqual(response.status_code, 200)
            session = self.client.get('/api/account/session/').json()
            self.assertTrue(session['authenticated'])
            self.assertEqual(session['destination'], destination)
            if destination == '/account/':
                self.assertEqual(self.client.get(COLLECTIONS).status_code, 403)
            self.assertEqual(self.client.post('/api/account/logout/').status_code, 200)
            self.assertFalse(self.client.get('/api/account/session/').json()['authenticated'])

    def test_shared_login_csrf_and_inactive_account(self):
        client = Client(enforce_csrf_checks=True)
        credentials = {'username': 'customer', 'password': 'Customer-test-password1'}
        self.assertEqual(client.post('/api/account/login/', credentials).status_code, 403)
        token = client.get('/api/account/session/').json()['csrf_token']
        self.assertEqual(client.post('/api/account/login/', credentials, HTTP_X_CSRFTOKEN=token).status_code, 200)
        self.assertEqual(client.post('/api/account/logout/').status_code, 403)
        self.customer.is_active = False
        self.customer.save(update_fields=['is_active'])
        self.assertEqual(self.client.post('/api/account/login/', credentials).status_code, 400)

    def test_bootstrap_and_authentication_boundaries(self):
        response = self.client.get(ROOT + 'session/')
        self.assertFalse(response.json()['authenticated'])
        self.assertEqual(response.json()['models'], [])
        self.assertIn('csrf_token', response.json())
        self.assertEqual(self.client.get(COLLECTIONS).status_code, 401)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(COLLECTIONS).status_code, 403)
        self.assertFalse(self.client.get(ROOT + 'session/').json()['authenticated'])
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(ROOT + 'session/').json()['models'], [])
        self.assertEqual(self.client.get(COLLECTIONS).status_code, 403)

    def test_staff_login_logout_and_nonstaff_login_denied(self):
        self.assertEqual(self.client.post(ROOT + 'login/', {'username':'customer', 'password':'Customer-test-password1'}).status_code, 400)
        self.assertEqual(self.client.post(ROOT + 'login/', {'username':'editor', 'password':'Editor-test-password1'}).status_code, 200)
        self.assertTrue(self.client.get(ROOT + 'session/').json()['authenticated'])
        self.assertEqual(self.client.get(ROOT + 'logout/').status_code, 405)
        self.assertEqual(self.client.post(ROOT + 'logout/').status_code, 200)
        self.assertEqual(self.client.get(COLLECTIONS).status_code, 401)

    def test_csrf_required_for_login_and_mutations(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(ROOT + 'login/', {'username':'owner','password':'Owner-test-password1'}).status_code, 403)
        token = client.get(ROOT + 'session/').json()['csrf_token']
        response = client.post(ROOT + 'login/', {'username':'owner','password':'Owner-test-password1'}, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.post(COLLECTIONS+'new/', {'name':'Bad','slug':'bad'}).status_code, 403)
        self.assertFalse(Category.objects.filter(slug='bad').exists())
        token = response.json()['csrf_token']
        self.assertEqual(client.post(COLLECTIONS+'new/', {'name':'Good','slug':'good','position':0,'is_active':'on'}, HTTP_X_CSRFTOKEN=token).status_code, 200)

    def test_group_permissions_control_directory_and_readonly_forms(self):
        self.grant('view_category')
        data = self.client.get(ROOT + 'session/').json()
        self.assertEqual([item['key'] for item in data['models']], ['sanjilas.category'])
        self.assertEqual(data['user']['roles'], ['Content team'])
        response = self.client.get(COLLECTIONS+f'{self.category.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['permissions']['change'])
        self.assertIn('name', [field['name'] for field in response.json()['fields']])
        self.assertEqual(self.client.post(COLLECTIONS+f'{self.category.pk}/', {'name':'Hacked'}).status_code, 403)
        self.assertEqual(self.client.get(COLLECTIONS+'new/').status_code, 403)
        self.assertEqual(self.client.post(COLLECTIONS+f'{self.category.pk}/delete/', {'confirm':'yes'}).status_code, 403)
        self.assertEqual(self.client.get(PRODUCTS).status_code, 403)

    def test_add_only_access(self):
        self.grant('add_category')
        model = self.client.get(ROOT+'session/').json()['models'][0]
        self.assertIsNone(model['count'])
        self.assertFalse(model['permissions']['view'])
        self.assertEqual(self.client.get(COLLECTIONS).status_code, 403)
        self.assertEqual(self.client.get(COLLECTIONS+'new/').status_code, 200)
        response = self.client.post(COLLECTIONS+'new/', {'name':'New','slug':'new','position':0,'is_active':'on'})
        self.assertEqual(response.status_code, 200)

    def test_crud_validation_and_audit_logs(self):
        self.grant('view_category','add_category','change_category','delete_category')
        self.assertEqual(self.client.post(COLLECTIONS+'new/', {'name':'Missing slug'}).status_code, 400)
        response = self.client.post(COLLECTIONS+'new/', {'name':'New','slug':'new','position':1,'is_active':'on'})
        self.assertEqual(response.status_code, 200)
        pk = response.json()['id']
        self.assertEqual(self.client.post(COLLECTIONS+f'{pk}/', {'name':'Updated','slug':'new','position':2,'is_active':'on'}).status_code, 200)
        self.assertEqual(Category.objects.get(pk=pk).name, 'Updated')
        self.assertFalse(self.client.get(COLLECTIONS+f'{pk}/delete/').json()['blocked'])
        self.assertEqual(self.client.post(COLLECTIONS+f'{pk}/delete/').status_code, 400)
        self.assertEqual(self.client.post(COLLECTIONS+f'{pk}/delete/', {'confirm':'yes'}).status_code, 200)
        self.assertFalse(Category.objects.filter(pk=pk).exists())
        self.assertEqual(set(LogEntry.objects.filter(user=self.staff).values_list('action_flag',flat=True)), {ADDITION,CHANGE,DELETION})

    def test_protected_relationships_and_singleton_rules(self):
        self.client.force_login(self.owner)
        self.assertTrue(self.client.get(COLLECTIONS+f'{self.category.pk}/delete/').json()['blocked'])
        self.assertEqual(self.client.post(COLLECTIONS+f'{self.category.pk}/delete/', {'confirm':'yes'}).status_code, 409)
        root = ROOT+'models/sanjilas/sitesettings/'
        self.assertEqual(self.client.get(root+'new/').status_code, 403)
        self.assertEqual(self.client.post(root+'1/delete/', {'confirm':'yes'}).status_code, 403)

    def test_dynamic_registry_scope_object_permissions_and_readonly(self):
        self.client.force_login(self.owner)
        class ScopedAdmin(ImportExportModelAdmin):
            readonly_fields = ('name',)
            def get_queryset(self, request):
                return super().get_queryset(request).filter(pk=self.allowed_pk)
            def has_change_permission(self, request, obj=None):
                return False if obj is not None else True
        scoped = ScopedAdmin(Category, admin.site)
        scoped.allowed_pk = self.category.pk
        other = Category.objects.create(name='Other', slug='other')
        with patch.dict(admin.site._registry, {Category: scoped}):
            response = self.client.get(COLLECTIONS)
            self.assertEqual(len(response.json()['rows']), 1)
            self.assertEqual(self.client.get(COLLECTIONS+f'{other.pk}/').status_code, 404)
            self.assertEqual(self.client.post(COLLECTIONS+f'{self.category.pk}/', {'slug':'changed'}).status_code, 403)
            data = self.client.get(COLLECTIONS+f'{self.category.pk}/').json()
            self.assertIn('name', [item['name'] for item in data['readonly']])

    def test_export_permissions_scope_and_formula_escaping(self):
        self.grant('view_category')
        Category.objects.create(name='=HYPERLINK("bad")',slug='formula')
        response = self.client.get(COLLECTIONS+'export/')
        self.assertEqual(response.status_code, 200)
        self.assertIn("'=HYPERLINK", response.content.decode())
        self.assertEqual(self.client.get(PRODUCTS+'export/').status_code, 403)
        self.assertIn('no-store', response['Cache-Control'])

    def test_staff_cannot_escalate_auth_permissions_and_hash_is_hidden(self):
        self.staff.user_permissions.set(Permission.objects.filter(content_type__app_label='auth',codename__in=['view_user','change_user','view_group','change_group']))
        self.client.force_login(self.staff)
        root = ROOT+'models/auth/user/'
        response = self.client.get(root+f'{self.staff.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.staff.password)
        self.assertFalse(response.json()['permissions']['change'])
        self.assertEqual(self.client.post(root+f'{self.staff.pk}/', {'is_superuser':'on','is_staff':'on'}).status_code, 403)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_superuser)

    def test_superuser_auth_forms_and_group_membership(self):
        self.client.force_login(self.owner)
        root = ROOT+'models/auth/user/'
        response = self.client.get(root+'new/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('password1', [field['name'] for field in response.json()['fields']])
        response = self.client.post(root+'new/', {'username':'new-staff', 'usable_password':'true', 'password1':'Strong-test-password123', 'password2':'Strong-test-password123'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(get_user_model().objects.get(username='new-staff').check_password('Strong-test-password123'))
        group = self.client.post(ROOT+'models/auth/group/new/', {'name':'Shop manager','permissions':[]})
        self.assertEqual(group.status_code, 200, group.content)

    def test_related_options_and_search(self):
        self.client.force_login(self.owner)
        response = self.client.get(PRODUCTS+'new/')
        self.assertEqual(response.status_code, 200)
        relation = next(field for field in response.json()['fields'] if field['name']=='category')
        self.assertEqual(relation['choices'][0]['value'], str(self.category.pk))
        self.assertEqual(self.client.get(PRODUCTS+'options/category/').status_code, 200)
        self.assertEqual(self.client.get(COLLECTIONS+'?q=rings').json()['count'], 1)
        self.assertEqual(self.client.get(ROOT+'models/unknown/unknown/').status_code, 404)

    def test_control_document_is_private_and_login_rate_limited(self):
        response = self.client.get('/control/')
        self.assertContains(response, 'noindex, nofollow')
        self.assertIn('no-store', response['Cache-Control'])
        for _ in range(10):
            self.client.post(ROOT+'login/', {'username':'bad','password':'bad'})
        self.assertEqual(self.client.post(ROOT+'login/', {'username':'bad','password':'bad'}).status_code, 429)

    def test_image_upload_and_clear_use_the_django_form(self):
        self.grant('view_category','add_category','change_category')
        buffer = io.BytesIO()
        Image.new('RGB',(8,8),'white').save(buffer,format='PNG')
        image = SimpleUploadedFile('test-image.png', buffer.getvalue(), content_type='image/png')
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            response = self.client.post(COLLECTIONS+'new/', {'name':'Images','slug':'images','position':0,'is_active':'on','image':image})
            self.assertEqual(response.status_code,200,response.content)
            pk = response.json()['id']
            schema = self.client.get(COLLECTIONS+f'{pk}/').json()
            self.assertTrue(next(field for field in schema['fields'] if field['name']=='image')['file_url'])
            response = self.client.post(COLLECTIONS+f'{pk}/', {'name':'Images','slug':'images','position':0,'is_active':'on','image-clear':'on'})
            self.assertEqual(response.status_code,200,response.content)
            self.assertFalse(Category.objects.get(pk=pk).image)

    def test_registration_automatically_exposes_a_new_control(self):
        self.client.force_login(self.owner)
        admin.site.register(Permission, ImportExportModelAdmin)
        try:
            urls = type('ControlTestUrls', (), {'urlpatterns': [path('admin/',admin.site.urls),path('api/',include('sanjilas.urls'))]})
            with override_settings(ROOT_URLCONF=urls):
                data = self.client.get(ROOT+'session/').json()
                self.assertIn('auth.permission', [model['key'] for model in data['models']])
                self.assertEqual(self.client.get(ROOT+'models/auth/permission/').status_code,200)
                self.assertEqual(self.client.get(ROOT+'models/auth/permission/new/').status_code,200)
        finally:
            admin.site.unregister(Permission)

    def test_revoked_role_permissions_take_effect_on_next_request(self):
        self.grant('view_category','change_category')
        self.assertEqual(self.client.get(COLLECTIONS).status_code,200)
        self.staff.groups.clear()
        self.assertEqual(self.client.get(COLLECTIONS).status_code,403)
        self.assertEqual(self.client.post(COLLECTIONS+f'{self.category.pk}/', {'name':'Changed'}).status_code,403)

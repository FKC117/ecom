from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from import_export.admin import ImportExportModelAdmin
from tablib import Dataset

from .models import SiteSettings, HomePage, Collection, Product, homepage_labels
from .resources import SiteSettingsResource, HomePageResource


class SiteSettingsTests(TestCase):
    def test_admin_settings_and_import_export_pages(self):
        user = get_user_model().objects.create_superuser('admin', 'admin@example.com', 'test-password')
        self.client.force_login(user)
        SiteSettings.objects.create()
        for path in ('/admin/sanjilas/sitesettings/', '/admin/sanjilas/sitesettings/1/change/', '/admin/sanjilas/sitesettings/import/', '/admin/sanjilas/sitesettings/export/'):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        request = self.client.get('/admin/sanjilas/sitesettings/').wsgi_request
        self.assertFalse(admin.site._registry[SiteSettings].has_add_permission(request))

    def test_singleton_model_and_database_constraint(self):
        SiteSettings.objects.create(site_name="Store")
        with self.assertRaises(ValidationError):
            SiteSettings(id=2).save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SiteSettings.objects.bulk_create([SiteSettings(id=2)])

    def test_api_fallbacks_and_llm_documents(self):
        settings = SiteSettings.objects.create(
            site_name="Custom Store", meta_description="Description",
            site_url="https://example.com", og_image="seo/share.png",
            llms_txt="# Store", llms_full_txt="# Full store",
        )
        response = self.client.get('/api/site-settings/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['meta_title'], settings.site_name)
        self.assertEqual(data['twitter_title'], settings.site_name)
        self.assertEqual(data['og_image'], 'https://example.com/media/seo/share.png')
        self.assertEqual(data['twitter_image'], data['og_image'])
        self.assertNotIn('llms_full_txt', data)
        self.assertEqual(self.client.get('/llms.txt').content, b'# Store')
        full = self.client.get('/llms-full.txt')
        self.assertEqual(full.content, b'# Full store')
        self.assertTrue(full['Content-Type'].startswith('text/plain'))
        self.assertEqual(self.client.post('/api/site-settings/').status_code, 405)

    def test_read_does_not_create_settings(self):
        self.assertEqual(self.client.get('/api/site-settings/').status_code, 200)
        self.assertFalse(SiteSettings.objects.exists())

    def test_import_export_round_trip_and_singleton_validation(self):
        settings = SiteSettings.objects.create(site_name='Round trip', logo='branding/logo.png')
        resource = SiteSettingsResource()
        data = resource.export()
        settings.site_name = 'Changed'
        settings.save()
        result = resource.import_data(data, dry_run=False, raise_errors=True)
        self.assertFalse(result.has_errors())
        settings.refresh_from_db()
        self.assertEqual(settings.site_name, 'Round trip')
        self.assertEqual(settings.logo.name, 'branding/logo.png')
        invalid = Dataset(headers=['id', 'site_name'])
        invalid.append([2, 'Invalid'])
        result = resource.import_data(invalid, dry_run=False)
        self.assertTrue(result.has_errors() or result.has_validation_errors())
        self.assertEqual(SiteSettings.objects.count(), 1)
        self.assertIsInstance(admin.site._registry[SiteSettings], ImportExportModelAdmin)

    def test_initial_html_metadata_is_escaped(self):
        SiteSettings.objects.create(site_name='<script>alert(1)</script>', meta_description='A "quote"')
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertContains(response, 'og:title')
        self.assertNotContains(response, '<script>alert(1)</script>')


class HomePageTests(TestCase):
    def test_backend_copy_and_palette_are_returned(self):
        SiteSettings.objects.create(palette="emerald", default_color_mode="dark")
        page = HomePage.objects.create(hero_title="An edited title", labels={**homepage_labels(), "hero_label": "Extra label", "nav_story": "Behind the jewellery"})
        response = self.client.get('/api/home/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['site']['palette'], 'emerald')
        self.assertEqual(data['site']['default_color_mode'], 'dark')
        self.assertEqual(data['page']['hero_title'], page.hero_title)
        self.assertEqual(data['page']['labels']['nav_story'], 'Behind the jewellery')
        self.assertEqual(self.client.post('/api/home/').status_code, 405)

    def test_hidden_products_and_collections_are_excluded(self):
        visible = Collection.objects.create(name='Rings', slug='rings')
        hidden = Collection.objects.create(name='Hidden', slug='hidden', is_active=False)
        Product.objects.create(name='Visible ring', slug='visible', collection=visible, price='1250.00')
        Product.objects.create(name='Hidden ring', slug='inactive', collection=visible, is_active=False)
        Product.objects.create(name='Hidden collection ring', slug='hidden', collection=hidden)
        data = self.client.get('/api/home/').json()
        self.assertEqual([item['name'] for item in data['collections']], ['Rings'])
        self.assertEqual([item['name'] for item in data['products']], ['Visible ring'])
        self.assertEqual(data['products'][0]['price'], '1250.00')

    def test_five_valid_palettes_and_invalid_palette_rejected(self):
        self.assertEqual(len(SiteSettings.Palette.choices), 5)
        for palette, _ in SiteSettings.Palette.choices:
            SiteSettings(palette=palette).full_clean()
        with self.assertRaises(ValidationError):
            SiteSettings(palette='custom').save()

    def test_initial_html_has_backend_theme_and_copy(self):
        SiteSettings.objects.create(palette='sapphire', default_color_mode='dark')
        HomePage.objects.create()
        response = self.client.get('/')
        self.assertContains(response, 'data-palette="sapphire" data-mode="dark"')
        self.assertContains(response, 'id="storefront-bootstrap"')

    def test_home_singleton_and_labels_survive_import_export(self):
        page = HomePage.objects.create(hero_title='Original')
        with self.assertRaises(ValidationError):
            HomePage(id=2).save()
        with self.assertRaises(ValidationError):
            HomePage(labels={}).save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            HomePage.objects.bulk_create([HomePage(id=2)])
        resource = HomePageResource()
        data = resource.export()
        page.hero_title = 'Edited'
        page.save()
        resource.import_data(data, dry_run=False, raise_errors=True)
        page.refresh_from_db()
        self.assertEqual(page.hero_title, 'Original')
        self.assertEqual(page.labels, homepage_labels())

    def test_all_models_have_admin_import_export(self):
        user = get_user_model().objects.create_superuser('owner', 'owner@example.com', 'test-password')
        self.client.force_login(user)
        for model in (HomePage, Collection, Product):
            self.assertIsInstance(admin.site._registry[model], ImportExportModelAdmin)
            path = f'/admin/sanjilas/{model._meta.model_name}/'
            for suffix in ('', 'add/', 'import/', 'export/'):
                self.assertEqual(self.client.get(path + suffix).status_code, 200, path + suffix)

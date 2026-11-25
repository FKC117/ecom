from django.contrib.auth import get_user_model
from django.test import TestCase


class StorefrontDocumentTests(TestCase):
    def test_parcel_label_document_serves_built_react_shell(self):
        response = self.client.get('/parcel-label/1/')
        self.assertContains(response, '<div id="root"></div>')
        self.assertContains(response, 'id="storefront-bootstrap"')
        self.assertContains(response, '/assets/')

    def test_existing_document_routes_serve_react_shell(self):
        for path in ('/', '/login/', '/account/', '/control/', '/sitemap/',
                     '/invoice/00000000-0000-0000-0000-000000000001/'):
            with self.subTest(path=path):
                self.assertContains(self.client.get(path), '<div id="root"></div>')

    def test_parcel_label_data_requires_authentication(self):
        self.assertEqual(self.client.get('/api/control/parcel-label/1/').status_code, 401)

    def test_parcel_label_data_denies_customer(self):
        user = get_user_model().objects.create_user(username='label-customer')
        self.client.force_login(user)
        self.assertEqual(self.client.get('/api/control/parcel-label/1/').status_code, 403)

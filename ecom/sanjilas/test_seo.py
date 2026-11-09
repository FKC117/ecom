from unittest.mock import patch
from xml.etree.ElementTree import fromstring

from django.test import TestCase

from .models import Category, HomePage, Product, SiteSettings


class SitemapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        SiteSettings.objects.create(site_url='https://shop.example.test')
        cls.category = Category.objects.create(name='Rings', slug='rings')
        cls.product = Product.objects.create(name='Ring', slug='ring', category=cls.category)

    def locations(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/xml', response['Content-Type'])
        return [element.text for element in fromstring(response.content).iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]

    def test_live_public_products_only_and_canonical_origin(self):
        self.assertEqual(self.locations('/sitemap.xml'), ['https://shop.example.test/', 'https://shop.example.test/sitemap/', 'https://shop.example.test/shop/', 'https://shop.example.test/categories/rings/', 'https://shop.example.test/products/ring/'])
        self.assertEqual(self.locations('/sitemap-1.xml'), self.locations('/sitemap.xml'))
        self.product.is_active = False
        self.product.save()
        self.assertEqual(self.locations('/sitemap.xml'), ['https://shop.example.test/', 'https://shop.example.test/sitemap/', 'https://shop.example.test/shop/', 'https://shop.example.test/categories/rings/'])
        self.product.is_active = True
        self.product.slug = 'renamed'
        self.product.save()
        self.assertIn('https://shop.example.test/products/renamed/', self.locations('/sitemap.xml'))
        self.category.is_active = False
        self.category.save()
        self.assertEqual(self.locations('/sitemap.xml'), ['https://shop.example.test/', 'https://shop.example.test/sitemap/', 'https://shop.example.test/shop/'])

    @patch('sanjilas.seo.PAGE_SIZE', 1)
    def test_pagination_and_invalid_pages(self):
        Product.objects.create(name='Second', slug='second', category=self.category)
        self.assertEqual(self.locations('/sitemap.xml'), ['https://shop.example.test/sitemap-1.xml', 'https://shop.example.test/sitemap-2.xml'])
        self.assertEqual(self.locations('/sitemap-2.xml'), ['https://shop.example.test/products/second/'])
        self.assertEqual(self.client.get('/sitemap-3.xml').status_code, 404)
        self.assertEqual(self.client.get('/sitemap-0.xml').status_code, 404)

    def test_empty_catalog_fallback_origin_and_robots(self):
        Product.objects.all().delete()
        SiteSettings.objects.update(site_url='')
        self.assertEqual(self.locations('/sitemap.xml'), ['http://testserver/', 'http://testserver/sitemap/', 'http://testserver/shop/', 'http://testserver/categories/rings/'])
        self.assertContains(self.client.get('/robots.txt'), 'Sitemap: http://testserver/sitemap.xml')
        self.assertEqual(self.client.head('/sitemap.xml').status_code, 200)
        self.assertEqual(self.client.post('/sitemap.xml').status_code, 405)

    def test_footer_copy_available_from_backend(self):
        HomePage.objects.create()
        self.assertEqual(self.client.get('/api/home/').json()['page']['labels']['sitemap'], 'Sitemap')

from django.contrib.auth import get_user_model
from django.test import TestCase
from .models import Category, HomePage, Product, ProductVariant, SiteSettings
from .commerce import set_item


class ProductPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        SiteSettings.objects.create(site_name='Sample Jewels',site_url='https://shop.example.test',delivery_inside_dhaka=60,delivery_outside_dhaka=120)
        HomePage.objects.create()
        cls.category=Category.objects.create(name='Rings',slug='rings')
        cls.product=Product.objects.create(name='Sample Ring',slug='sample-ring',category=cls.category,price=100,stock_quantity=5,description='A detailed ring description.',sku='RING-001')

    def test_product_endpoint_has_details_variants_and_related_active_products(self):
        variant=ProductVariant.objects.create(product=self.product,name='Small',sku='SMALL-001',price=120,stock_quantity=2)
        ProductVariant.objects.create(product=self.product,name='Hidden',sku='HIDDEN-001',is_active=False)
        for i in range(6): Product.objects.create(name=f'Related {i}',slug=f'related-{i}',category=self.category,price=100)
        Product.objects.create(name='Hidden',slug='hidden',category=self.category,is_active=False)
        category=Category.objects.create(name='Other',slug='other')
        Product.objects.create(name='Other',slug='other',category=category)
        data=self.client.get('/api/shop/products/sample-ring/').json()
        self.assertEqual(data['product']['sku'],'RING-001')
        self.assertEqual([row['id'] for row in data['product']['variants']],[variant.pk])
        self.assertEqual(len(data['products']),4)
        self.assertTrue(all(row['category']==self.category.pk and row['id']!=self.product.pk for row in data['products']))
        self.assertEqual(data['site']['delivery_inside_dhaka'],'60.00')
        self.assertEqual(data['page']['labels']['product_zoom'],'View larger image')

    def test_stock_reservations_and_own_cart_are_respected(self):
        user=get_user_model().objects.create_user('product-page-buyer')
        set_item(user,self.product.pk,None,2)
        self.assertEqual(self.client.get('/api/shop/products/sample-ring/').json()['product']['available_quantity'],3)
        self.client.force_login(user)
        self.assertEqual(self.client.get('/api/shop/products/sample-ring/').json()['product']['available_quantity'],5)

    def test_recommendations_fill_from_other_active_categories(self):
        category=Category.objects.create(name='Necklaces',slug='necklaces')
        other=Product.objects.create(name='Pendant',slug='pendant',category=category)
        data=self.client.get('/api/shop/products/sample-ring/').json()
        self.assertEqual([row['id'] for row in data['products']],[other.pk])

    def test_initial_html_has_product_metadata_and_canonical_without_javascript(self):
        response=self.client.get('/products/sample-ring/')
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'<title>Sample Ring | Sample Jewels</title>',html=True)
        self.assertContains(response,'https://shop.example.test/products/sample-ring/')
        self.assertContains(response,'A detailed ring description.')
        self.assertContains(response,'content="product"')
        self.product.name='<script>alert(1)</script>';self.product.save()
        html=self.client.get('/products/sample-ring/').content.decode()
        self.assertNotIn('<title><script>',html)
        self.assertIn('&lt;script&gt;',html)

    def test_missing_inactive_products_or_categories_return_404(self):
        self.assertEqual(self.client.get('/products/missing/').status_code,404)
        self.assertEqual(self.client.get('/api/shop/products/missing/').status_code,404)
        self.assertEqual(self.client.get('/api/shop/products/missing/').json()['site']['robots'],'noindex, nofollow')
        self.product.is_active=False;self.product.save()
        self.assertEqual(self.client.get('/products/sample-ring/').status_code,404)
        self.product.is_active=True;self.product.save()
        self.category.is_active=False;self.category.save()
        self.assertEqual(self.client.get('/api/shop/products/sample-ring/').status_code,404)

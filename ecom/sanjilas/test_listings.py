from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.test.utils import CaptureQueriesContext
from django.db import connection
from .models import Category,Collection,Product,ProductVariant,SiteSettings,HomePage
from .commerce import set_item


class ListingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        SiteSettings.objects.create(site_name='Sample shop',site_url='https://shop.example.test')
        HomePage.objects.create()
        cls.category=Category.objects.create(name='Bangles',slug='bangles',description='Sample category description')
        cls.collection=Collection.objects.create(name='Everyday',slug='everyday')
        for i in range(51):
            product=Product.objects.create(name=f'Bangle {i:03}',category=cls.category,price=100+i,stock_quantity=10)
            if i%2==0:product.collections.add(cls.collection)

    def api(self,suffix=''): return self.client.get('/api/shop/categories/bangles/'+suffix)

    def test_database_pagination_and_lightweight_cards(self):
        first=self.api().json();second=self.api('?page=2').json();last=self.api('?page=3').json()
        self.assertEqual(first['listing']['count'],51)
        self.assertEqual([len(data['products']) for data in [first,second,last]],[24,24,3])
        self.assertFalse(set(row['id'] for row in first['products'])&set(row['id'] for row in second['products']))
        self.assertNotIn('gallery',first['products'][0]);self.assertNotIn('variants',first['products'][0])
        self.assertEqual(len(self.client.get('/api/home/').json()['products']),8)
        self.assertEqual(self.api('?page=4').status_code,404)
        self.assertEqual(self.client.get('/categories/bangles/?page=4').status_code,404)

    def test_collection_scope_search_sort_and_price_filters(self):
        collection=self.client.get('/api/shop/collections/everyday/').json()
        self.assertEqual(collection['listing']['count'],26)
        data=self.api('?min_price=120&max_price=125&sort=price_desc').json()
        self.assertEqual([Decimal(row['discounted_price']) for row in data['products']],[Decimal(i) for i in range(125,119,-1)])
        self.assertEqual(self.api('?q=Bangle+050').json()['listing']['count'],1)
        self.assertEqual(self.api('?sort=name').json()['products'][0]['name'],'Bangle 000')
        self.assertEqual(self.api('?sort=newest').json()['products'][0]['name'],'Bangle 050')

    def test_variant_discount_price_stock_and_reservations_match_cards(self):
        product=Product.objects.create(name='Variants',category=self.category,price=1000,discount_type='percent',discount_value=10)
        ProductVariant.objects.create(product=product,name='Out',price=10,stock_quantity=0)
        buyable=ProductVariant.objects.create(product=product,name='Available',price=500,stock_quantity=1)
        ProductVariant.objects.create(product=product,name='Hidden',price=1,stock_quantity=10,is_active=False)
        data=self.api('?q=Variants&min_price=450&max_price=450&in_stock=1').json()
        self.assertEqual(data['listing']['count'],1);self.assertEqual(data['products'][0]['discounted_price'],'450.00')
        user=get_user_model().objects.create_user('listing-reserver');set_item(user,product.pk,buyable.pk,1)
        self.assertEqual(self.api('?q=Variants&in_stock=1').json()['listing']['count'],0)
        self.client.force_login(user)
        self.assertEqual(self.api('?q=Variants&in_stock=1').json()['listing']['count'],1)

    def test_invalid_queries_inactive_groups_and_empty_categories(self):
        for suffix in ['?sort=bad','?min_price=NaN','?max_price=-1','?min_price=5&max_price=1']:
            response=self.api(suffix);self.assertEqual(response.status_code,400);self.assertTrue(response.json()['error'])
        for page in ['0','-1','abc','999999999999999999999999999999']:
            self.assertEqual(self.api('?page='+page).status_code,404)
        Category.objects.create(name='Empty',slug='empty')
        self.assertEqual(self.client.get('/api/shop/categories/empty/').json()['listing']['count'],0)
        self.category.is_active=False;self.category.save()
        self.assertEqual(self.api().status_code,404)
        self.assertEqual(self.client.get('/categories/bangles/').status_code,404)

    def test_metadata_legacy_redirects_and_bounded_queries(self):
        response=self.client.get('/categories/bangles/?page=2')
        self.assertContains(response,'Bangles | Sample shop')
        self.assertContains(response,'https://shop.example.test/categories/bangles/?page=2')
        self.assertContains(response,'Sample category description')
        self.assertContains(self.client.get('/categories/bangles/?sort=price_asc'),'noindex, follow')
        legacy=self.client.get(f'/?category={self.category.pk}#jewellery')
        self.assertEqual(legacy.status_code,301);self.assertEqual(legacy['Location'],'/categories/bangles/')
        with CaptureQueriesContext(connection) as captured:self.api()
        self.assertLess(len(captured),25)

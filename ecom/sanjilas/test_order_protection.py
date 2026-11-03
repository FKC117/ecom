import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from types import SimpleNamespace

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from import_export.admin import ImportExportModelAdmin

from .commerce import ShopError, place_order, set_item, transition_order
from .models import Area, CartItem, Category, City, CommerceBlock, CommerceLimit, Order, OrderReview, Product, SiteSettings
from .order_protection import normalize_phone, preflight


DETAILS = {'customer_name':'Sample customer','phone':'01700000001','address':'Sample address','city':'Dhaka','area':'Sample area'}


class OrderProtectionTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.user=User.objects.create_user('protection-buyer')
        self.other=User.objects.create_user('protection-other')
        self.root=User.objects.create_superuser('protection-root')
        self.site=SiteSettings.objects.create()
        category=Category.objects.create(name='Rings',slug='rings')
        self.product=Product.objects.create(name='Sample ring',slug='sample-ring',category=category,price=100,stock_quantity=100)
        city=City.objects.create(name='Dhaka');area=Area.objects.create(city=city,name='Sample area')
        self.form={**DETAILS,'city':str(city.pk),'area':str(area.pk)}
        self.client.force_login(self.user)

    def order(self,quantity=1,user=None,**details):
        user=user or self.user
        set_item(user,self.product.pk,None,quantity)
        return place_order(user,uuid.uuid4(),{**DETAILS,**details})

    def post_order(self,**values):
        cart=self.client.get('/api/shop/cart/').json()
        return self.client.post('/api/shop/checkout/',{**self.form,'checkout_key':str(uuid.uuid4()),'quote':cart['quote'],**values})

    def test_phone_normalization_and_invalid_phone(self):
        for phone in ['01700 000001','+8801700000001','008801700000001','8801700000001','০১৭০০০০০০০১']:
            self.assertEqual(normalize_phone(phone),'01700000001')
        for phone in ['123','abc01700000001','017000000012','+441234567890']:
            with self.assertRaises(ValidationError): normalize_phone(phone)
        set_item(self.user,self.product.pk,None,1)
        self.assertEqual(self.post_order(phone='wrong').status_code,400)
        self.assertFalse(Order.objects.exists())

    def test_duplicate_across_accounts_phone_formats_and_idempotency(self):
        first=self.order()
        set_item(self.other,self.product.pk,None,1)
        with self.assertRaises(ShopError) as caught:
            place_order(self.other,uuid.uuid4(),{**DETAILS,'phone':'+8801700000001'})
        self.assertEqual(caught.exception.key,'shop_duplicate_order')
        self.assertEqual(Order.objects.count(),1)
        self.assertTrue(CartItem.objects.filter(cart__user=self.other).exists())
        self.assertEqual(place_order(self.user,first.checkout_key,DETAILS).pk,first.pk)
        Order.objects.filter(pk=first.pk).update(created_at=timezone.now()-timedelta(minutes=11))
        self.assertIsNotNone(place_order(self.other,uuid.uuid4(),DETAILS).pk)

    def test_counter_limits_failed_attempts_and_removal_still_allowed(self):
        self.site.reservation_attempt_limit=1;self.site.save()
        values={'product_id':self.product.pk,'quantity':1}
        self.assertEqual(self.client.post('/api/shop/cart/items/',values).status_code,200)
        expiry=CartItem.objects.get().expires_at
        self.assertEqual(self.client.post('/api/shop/cart/items/',values).status_code,429)
        self.assertEqual(CartItem.objects.get().expires_at,expiry)
        self.assertEqual(self.client.post('/api/shop/cart/items/',{**values,'quantity':0}).status_code,200)
        self.assertFalse(CartItem.objects.exists())
        self.assertTrue(CommerceLimit.objects.exists())
        self.site.checkout_attempt_limit=1;self.site.save()
        context=SimpleNamespace(user=self.user,commerce_context={'browser_key':'a'*64})
        preflight(context,'checkout',DETAILS['phone'])
        with self.assertRaises(ShopError) as caught: preflight(context,'checkout',DETAILS['phone'])
        self.assertEqual(caught.exception.status,429)

    def test_cart_limit_blocks_hoarding_without_stock_change(self):
        self.site.cart_unit_limit=2;self.site.save()
        with self.assertRaises(ShopError): set_item(self.user,self.product.pk,None,3)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,100)
        self.assertFalse(CartItem.objects.exists())

    def test_invalid_checkout_counts_and_successful_retry_skips_limit(self):
        self.site.checkout_attempt_limit=1;self.site.save()
        self.assertEqual(self.client.post('/api/shop/checkout/',{}).status_code,400)
        result=self.client.post('/api/shop/checkout/',{})
        self.assertEqual(result.status_code,429)
        self.assertEqual(result['Retry-After'],'600')
        order=self.order()
        self.assertEqual(self.post_order(checkout_key=str(order.checkout_key)).status_code,200)

    def test_account_and_browser_block_do_not_prevent_removal(self):
        set_item(self.user,self.product.pk,None,1)
        block=CommerceBlock.objects.create(kind='user',value=str(self.user.pk),reason='Sample review',expires_at=timezone.now()+timedelta(hours=1))
        values={'product_id':self.product.pk,'quantity':1}
        self.assertEqual(self.client.post('/api/shop/cart/items/',values).status_code,403)
        self.assertEqual(self.client.post('/api/shop/cart/items/',{**values,'quantity':0}).status_code,200)
        block.is_active=False;block.save()
        self.assertEqual(self.client.post('/api/shop/cart/items/',values).status_code,200)
        from .models import Cart
        cart=Cart.objects.get(user=self.user)
        CommerceBlock.objects.create(kind='browser',value=cart.browser_key,reason='Sample browser review',expires_at=timezone.now()+timedelta(hours=1))
        self.assertEqual(self.client.post('/api/shop/cart/items/',values).status_code,403)

    def test_review_endpoint_requires_csrf(self):
        from django.test import Client
        order=self.order()
        client=Client(enforce_csrf_checks=True);client.force_login(self.root)
        self.assertEqual(client.post(f'/api/control/operations/orders/{order.pk}/review/',{'decision':'rejected','reason':'No token','expected':'clear'}).status_code,403)
        order.refresh_from_db();self.assertEqual(order.status,'placed')

    def test_temporary_phone_block_is_normalized_and_private(self):
        block=CommerceBlock.objects.create(kind='phone',value='+8801700000001',reason='Internal review only',expires_at=timezone.now()+timedelta(hours=1))
        self.assertEqual(block.value,DETAILS['phone'])
        set_item(self.user,self.product.pk,None,1)
        result=self.post_order()
        self.assertEqual(result.status_code,403)
        self.assertNotIn('Internal review',str(result.content))
        block.expires_at=timezone.now()-timedelta(seconds=1);block.save()
        self.assertEqual(self.post_order().status_code,200)
        for model in [CommerceBlock,CommerceLimit,OrderReview]: self.assertIsInstance(admin.site._registry[model],ImportExportModelAdmin)

    def test_shared_ip_is_review_only_and_dummy_payment_does_not_bypass(self):
        self.site.order_review_ip_limit=1;self.site.dummy_payments_enabled=True;self.site.save()
        self.order(checkout_ip='198.51.100.7')
        flagged=self.order(quantity=2,user=self.other,phone='01700000002',checkout_ip='198.51.100.7',payment_method='pay_now')
        self.assertEqual(flagged.review_status,'pending')
        self.assertIn('busy_ip',flagged.review_reasons)
        with self.assertRaises(ValidationError): transition_order(flagged.pk,'processing',actor=self.root)
        self.client.force_login(self.other)
        public=self.client.get('/api/shop/orders/').json()
        self.assertNotIn('review_status',str(public));self.assertNotIn('busy_ip',str(public))
        invoice=self.client.get(f'/api/shop/orders/{flagged.pk}/invoice/').json()
        self.assertNotIn('review_reasons',str(invoice))

    def test_review_queue_permissions_approval_rejection_and_audit(self):
        self.site.order_review_phone_limit=1;self.site.save()
        self.order()
        flagged=self.order(quantity=2)
        self.assertEqual(flagged.review_status,'pending')
        path=f'/api/control/operations/orders/{flagged.pk}/review/'
        staff=get_user_model().objects.create_user('ordinary-staff',is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.post(path,{'decision':'approved','reason':'Checked','expected':'pending'}).status_code,403)
        self.client.force_login(self.root)
        queue=self.client.get('/api/control/operations/orders/?review=pending').json()
        self.assertEqual([row['id'] for row in queue['rows']],[str(flagged.pk)])
        self.assertEqual(self.client.post(path,{'decision':'approved','reason':'Confirmed by phone','expected':'pending'}).status_code,200)
        transition_order(flagged.pk,'processing',actor=self.root)
        self.assertEqual(self.client.post(path,{'decision':'rejected','reason':'Duplicate confirmed','expected':'pending'}).status_code,409)
        self.assertEqual(self.client.post(path,{'decision':'rejected','reason':'Duplicate confirmed','expected':'approved'}).status_code,200)
        flagged.refresh_from_db();self.assertEqual(flagged.status,'cancelled');self.assertEqual(flagged.review_status,'rejected')
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,99)
        self.assertEqual(OrderReview.objects.filter(order=flagged).count(),2)
        self.assertEqual(self.client.post(path,{'decision':'rejected','reason':'Again','expected':'rejected'}).status_code,400)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,99)
        detail=self.client.get(f'/api/control/operations/orders/{flagged.pk}/').json()
        self.assertEqual(len(detail['review']['history']),2)


class ConcurrentDuplicateTests(TransactionTestCase):
    def test_two_accounts_cannot_place_same_order_concurrently(self):
        users=[get_user_model().objects.create_user(f'concurrent-protection-{i}') for i in range(2)]
        SiteSettings.objects.create()
        category=Category.objects.create(name='Sample',slug='sample')
        product=Product.objects.create(name='Sample',slug='sample',category=category,price=100,stock_quantity=5)
        for user in users: set_item(user,product.pk,None,1)
        barrier=Barrier(2)
        def checkout(user):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try: place_order(user,uuid.uuid4(),dict(DETAILS));return 'placed'
                except ShopError as error: return error.key
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool: result=list(pool.map(checkout,users))
        self.assertCountEqual(result,['placed','shop_duplicate_order'])
        self.assertEqual(Order.objects.count(),1)
        product.refresh_from_db();self.assertEqual(product.stock_quantity,4)

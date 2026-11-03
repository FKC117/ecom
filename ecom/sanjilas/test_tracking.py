import json,uuid
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase,Client,RequestFactory,override_settings
from django.utils import timezone
from .models import Category,Product,City,Area,SiteSettings,Order,Cart,CartItem,CommerceActivity
from .tracking import client_ip

class ClientIPTests(TestCase):
    @override_settings(COMMERCE_TRUSTED_PROXIES=[])
    def test_untrusted_peer_cannot_spoof_forwarded_headers(self):
        req=RequestFactory().get('/',REMOTE_ADDR='203.0.113.4',HTTP_X_FORWARDED_FOR='198.51.100.7')
        self.assertEqual(client_ip(req),'203.0.113.4')
    @override_settings(COMMERCE_TRUSTED_PROXIES=['127.0.0.1/32','10.0.0.0/8'])
    def test_trusted_chain_uses_nearest_untrusted_hop(self):
        req=RequestFactory().get('/',REMOTE_ADDR='127.0.0.1',HTTP_X_FORWARDED_FOR='203.0.113.99, 198.51.100.7, 10.0.0.2')
        self.assertEqual(client_ip(req),'198.51.100.7')
        req.META['HTTP_X_FORWARDED_FOR']='invalid, 198.51.100.7'
        self.assertEqual(client_ip(req),'127.0.0.1')

class TrackingTests(TestCase):
    def setUp(self):
        cache.clear()
        User=get_user_model();self.buyer=User.objects.create_user('tracking-buyer');self.owner=User.objects.create_superuser('tracking-owner')
        SiteSettings.objects.create()
        category=Category.objects.create(name='Rings',slug='rings')
        self.product=Product.objects.create(name='Ring',slug='ring',category=category,price=100,stock_quantity=5)
        city=City.objects.create(name='Dhaka');area=Area.objects.create(city=city,name='Mohammadpur')
        self.details={'customer_name':'Sample','phone':'01000000000','address':'Sample address','city':str(city.pk),'area':str(area.pk)}
        self.client.force_login(self.buyer)
    def reserve(self):
        response=self.client.post('/api/shop/cart/items/',{'product_id':self.product.pk,'quantity':1},REMOTE_ADDR='198.51.100.7',HTTP_USER_AGENT='Preview Browser/1.0')
        self.assertEqual(response.status_code,200,response.content)
        return response.json()
    def checkout(self):
        cart=self.reserve();values={**self.details,'quote':cart['quote'],'checkout_key':str(uuid.uuid4()),'checkout_ip':'203.0.113.99','browser_key':'forged'}
        response=self.client.post('/api/shop/checkout/',values,REMOTE_ADDR='198.51.100.7',HTTP_USER_AGENT='Preview Browser/1.0')
        self.assertEqual(response.status_code,200,response.content)
        return Order.objects.get(pk=response.json()['order']['id']),values,response
    def test_checkout_stores_server_context_and_retry_does_not_rewrite_it(self):
        order,values,response=self.checkout()
        self.assertEqual(order.checkout_ip,'198.51.100.7');self.assertEqual(order.user_agent,'Preview Browser/1.0')
        self.assertTrue(order.browser_key);self.assertNotEqual(order.browser_key,'forged')
        self.assertTrue(CommerceActivity.objects.filter(order=order,kind='checkout',response_status=200).exists())
        self.assertNotIn('checkout_ip',response.json()['order']);self.assertNotIn('browser_key',response.json()['order'])
        self.assertEqual(self.client.post('/api/shop/checkout/',values,REMOTE_ADDR='203.0.113.9').status_code,200)
        order.refresh_from_db();self.assertEqual(order.checkout_ip,'198.51.100.7')
        invoice=self.client.get(f'/api/shop/orders/{order.pk}/invoice/').json()['order']
        self.assertNotIn('browser_key',invoice);self.assertNotIn('checkout_ip',invoice)
    def test_browser_cookie_is_signed_and_cart_view_does_not_extend_hold(self):
        self.reserve();cart=Cart.objects.get(user=self.buyer);key=cart.browser_key;expiry=CartItem.objects.get().expires_at
        response=self.client.get('/api/shop/cart/',REMOTE_ADDR='198.51.100.8')
        cart.refresh_from_db();self.assertEqual(cart.browser_key,key);self.assertEqual(cart.last_ip,'198.51.100.8')
        self.assertEqual(CartItem.objects.get().expires_at,expiry)
        self.assertTrue(response.cookies['commerce_browser']['httponly']);self.assertEqual(response.cookies['commerce_browser']['samesite'],'Lax')
        self.client.cookies['commerce_browser']='forged'
        self.client.get('/api/shop/cart/');cart.refresh_from_db();self.assertNotEqual(cart.browser_key,key)
    def test_failed_checkout_and_csrf_rejection_are_recorded(self):
        self.assertEqual(self.client.post('/api/shop/checkout/',{},REMOTE_ADDR='198.51.100.7').status_code,400)
        self.assertTrue(CommerceActivity.objects.filter(kind='checkout',response_status=400).exists())
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.buyer)
        self.assertEqual(csrf.post('/api/shop/cart/items/',{}).status_code,403)
        self.assertTrue(CommerceActivity.objects.filter(kind='cart_change',response_status=403).exists())
    def test_tracking_requires_separate_staff_permission_and_is_hidden_from_generic_forms(self):
        order,_,_=self.checkout()
        staff=get_user_model().objects.create_user('tracking-staff',is_staff=True)
        staff.user_permissions.set(Permission.objects.filter(content_type__app_label='sanjilas',codename__in=['view_order','view_orderitem','view_commerceactivity']))
        self.client.force_login(staff)
        self.assertIsNone(self.client.get(f'/api/control/operations/orders/{order.pk}/').json()['tracking'])
        form=self.client.get(f'/api/control/models/sanjilas/order/{order.pk}/')
        self.assertNotIn('checkout_ip',form.content.decode());self.assertNotIn('browser_key',form.content.decode())
        self.assertFalse(form.json()['model']['can_export'])
        self.assertEqual(self.client.get('/api/control/models/sanjilas/commerceactivity/').status_code,403)
        staff.user_permissions.add(Permission.objects.get(content_type__app_label='sanjilas',codename='view_order_tracking'))
        self.client.force_login(staff)
        self.assertEqual(self.client.get(f'/api/control/operations/orders/{order.pk}/').json()['tracking']['ip'],'198.51.100.7')
        self.assertEqual(self.client.get('/api/control/operations/orders/',{'q':'198.51.100.7'}).json()['count'],1)
        self.client.force_login(self.owner)
        data=self.client.get(f'/api/control/operations/orders/{order.pk}/').json()['tracking']
        self.assertEqual(data['ip'],'198.51.100.7');self.assertTrue(data['events'])
    def test_retention_clears_tracking_without_changing_order_amounts(self):
        order,_,_=self.checkout();old=timezone.now()-timedelta(days=31)
        CommerceActivity.objects.update(created_at=old);Order.objects.filter(pk=order.pk).update(checkout_recorded_at=old)
        Cart.objects.filter(user=self.buyer).update(last_activity_at=old)
        call_command('purge_commerce_tracking',verbosity=0)
        order.refresh_from_db();self.assertIsNone(order.checkout_ip);self.assertEqual(order.browser_key,'');self.assertEqual(order.total,100)
        self.assertFalse(CommerceActivity.objects.exists());self.assertEqual(Cart.objects.get(user=self.buyer).browser_key,'')

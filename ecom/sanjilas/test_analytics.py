import json
import uuid
from datetime import timedelta
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from .commerce import set_item, place_order
from .models import CartJourney, CartItem, Category, Product, SiteSettings
from .test_commerce import DETAILS


class AnalyticsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('analytics-buyer')
        SiteSettings.objects.create()
        category = Category.objects.create(name='Test', slug='analytics-test')
        self.product = Product.objects.create(name='Test ring', slug='analytics-ring', category=category, price=100, track_stock=True, stock_quantity=10)
        self.client.force_login(self.user)

    def test_cart_delta_is_server_calculated_and_failed_add_has_no_event(self):
        url = '/api/shop/cart/items/'
        response = self.client.post(url, {'product_id':self.product.pk, 'quantity':2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['analytics_add']['quantity'], 2)
        response = self.client.post(url, {'product_id':self.product.pk, 'quantity':3})
        self.assertEqual(response.json()['analytics_add']['quantity'], 1)
        response = self.client.post(url, {'product_id':self.product.pk, 'quantity':1})
        self.assertIsNone(response.json()['analytics_add'])
        self.assertEqual(self.client.post(url, {'product_id':self.product.pk, 'quantity':99}).status_code, 409)

    def test_expired_journey_survives_new_window_and_reads_do_not_extend_it(self):
        cart = set_item(self.user, self.product.pk, None, 1)
        journey = CartJourney.objects.get(cart=cart)
        expiry = journey.expires_at
        self.client.get('/api/shop/cart/')
        journey.refresh_from_db()
        self.assertEqual(journey.expires_at, expiry)
        past = timezone.now() - timedelta(seconds=1)
        CartItem.objects.filter(cart=cart).update(expires_at=past)
        CartJourney.objects.filter(pk=journey.pk).update(expires_at=past)
        journey.refresh_from_db()
        self.assertEqual(journey.status, 'abandoned')
        set_item(self.user, self.product.pk, None, 2)
        self.assertEqual(CartJourney.objects.filter(cart=cart).count(), 2)

    def test_checkout_marker_ignores_contact_details_and_conversion_is_idempotent(self):
        cart = set_item(self.user, self.product.pk, None, 1)
        payload = self.client.get('/api/shop/cart/').json()
        response = self.client.post('/api/shop/cart/draft/', {'expiry':payload['draft_expiry'], 'draft':json.dumps({'checkout_open':True, 'phone':'private'})})
        self.assertEqual(response.status_code, 200)
        journey = CartJourney.objects.get(cart=cart)
        self.assertIsNotNone(journey.checkout_started_at)
        self.assertNotIn('private', json.dumps(journey.items))
        key = uuid.uuid4()
        order = place_order(self.user, key, DETAILS)
        self.assertEqual(place_order(self.user, key, DETAILS).pk, order.pk)
        journey.refresh_from_db()
        self.assertEqual(journey.status, 'converted')
        self.assertEqual(journey.order_id, order.pk)
        self.assertNotIn('journey', json.dumps(self.client.get('/api/shop/cart/').json()))

    def test_empty_cart_and_readonly_admin(self):
        cart = set_item(self.user, self.product.pk, None, 1)
        set_item(self.user, self.product.pk, None, 0)
        self.assertEqual(CartJourney.objects.get(cart=cart).status, 'emptied')
        from django.test import RequestFactory
        request = RequestFactory().get('/')
        request.user = get_user_model().objects.create_superuser('analytics-admin', password='test')
        ma = admin.site._registry[CartJourney]
        self.assertFalse(ma.has_add_permission(request))
        self.assertFalse(ma.has_change_permission(request))
        self.assertFalse(ma.has_delete_permission(request))

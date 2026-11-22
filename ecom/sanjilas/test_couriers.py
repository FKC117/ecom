import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from .commerce import place_order, set_item, transition_order
from .couriers import CourierError, Pathao
from .models import Category, CourierAccount, CourierToken, Product, Shipment, SiteSettings


CREDENTIALS = {'client_id': 'test-id', 'client_secret': 'test-secret', 'username': 'test-user', 'password': 'test-password'}


@override_settings(PATHAO={'sandbox': CREDENTIALS, 'live': CREDENTIALS}, PATHAO_LIVE_ENABLED=False)
class CourierTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_superuser('courier-owner')
        self.customer = get_user_model().objects.create_user('courier-customer')
        self.staff = get_user_model().objects.create_user('courier-staff', is_staff=True)
        SiteSettings.objects.create()
        category = Category.objects.create(name='Test', slug='courier-test')
        product = Product.objects.create(name='Test item', slug='courier-item', category=category, price=100, stock_quantity=10)
        set_item(self.customer, product.pk, None, 1)
        self.order = place_order(self.customer, uuid.uuid4(), {'customer_name': 'Test Customer', 'email': '', 'phone': '+8801700000000', 'address': 'Synthetic address for testing', 'city': 'Dhaka', 'area': 'Test area', 'postal_code': '', 'notes': ''})
        self.account = CourierAccount.objects.create(name='Pathao test', store_id=1)
        self.base = f'/api/control/operations/orders/{self.order.pk}/courier/'
        self.client.force_login(self.owner)
        self.form = {'account': self.account.pk, 'expected_version': self.order.revision, 'item_weight': '0.5', 'item_quantity': 1, 'delivery_type': 48}

    def booking(self, **changes):
        return self.client.post(self.base + 'book/', {**self.form, **changes})

    @patch.object(Pathao, 'token', return_value='token')
    @patch.object(Pathao, 'book', return_value={'data': {'consignment_id': 'TEST-1', 'order_status': 'Pending', 'delivery_fee': 80}})
    def test_booking_snapshot_and_duplicate_protection(self, book, token):
        response = self.booking()
        self.assertEqual(response.status_code, 200, response.content)
        payload = book.call_args.args[0]
        self.assertEqual(payload['recipient_phone'], '01700000000')
        self.assertEqual(payload['amount_to_collect'], int(self.order.total))
        self.assertNotIn('recipient_city', payload)
        self.assertNotIn('checkout_ip', payload)
        self.assertEqual(self.booking().status_code, 400)
        book.assert_called_once()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'placed')
        self.assertEqual(self.order.revision, 1)
        self.assertEqual(Shipment.objects.get().environment, 'sandbox')

    @patch.object(Pathao, 'token', return_value='token')
    @patch.object(Pathao, 'book', side_effect=CourierError('Timed out'))
    def test_uncertain_result_is_persistent_and_not_retried(self, book, token):
        self.assertEqual(self.booking().status_code, 409)
        self.assertEqual(Shipment.objects.get().state, 'uncertain')
        self.assertEqual(self.booking().status_code, 400)
        book.assert_called_once()

    @patch.object(Pathao, 'token', return_value='token')
    @patch.object(Pathao, 'book', side_effect=[CourierError('Rejected', rejected=True), {'data': {'consignment_id': 'TEST-2', 'delivery_fee': 80}}])
    def test_explicit_rejection_can_be_retried(self, book, token):
        self.assertEqual(self.booking().status_code, 409)
        reference = Shipment.objects.get().merchant_order_id
        self.assertEqual(self.booking().status_code, 200)
        self.assertEqual(Shipment.objects.count(), 1)
        self.assertEqual(Shipment.objects.get().merchant_order_id, reference)

    @patch.object(Pathao, 'token', return_value='token')
    @patch.object(Pathao, 'book', return_value={'data': True})
    def test_malformed_response_requires_reconciliation(self, book, token):
        self.assertEqual(self.booking().status_code, 409)
        self.assertEqual(Shipment.objects.get().state, 'uncertain')

    @patch.object(Pathao, 'token', return_value='token')
    @patch.object(Pathao, 'book')
    def test_validation_prevents_external_calls(self, book, token):
        for changes in [{'item_weight': '.1'}, {'item_quantity': 0}, {'recipient_area': 12}, {'expected_version': 99}]:
            self.assertEqual(self.booking(**changes).status_code, 400)
        transition_order(self.order.pk, 'cancelled')
        self.form['expected_version'] = 2
        self.assertEqual(self.booking().status_code, 400)
        book.assert_not_called()
        self.assertFalse(Shipment.objects.exists())

    @patch.object(Pathao, 'token', return_value='token')
    @patch.object(Pathao, 'book', return_value={'data': {'consignment_id': 'PAID-TEST', 'delivery_fee': 80}})
    def test_cod_uses_partial_and_full_payment_balance(self, book, token):
        for amount, expected in [(50, int(self.order.total)-50), (int(self.order.total)-50, 0)]:
            response = self.client.post(f'/api/control/operations/orders/{self.order.pk}/payments/', {
                'kind': 'payment', 'amount': amount, 'method': 'cash', 'reference': '',
                'occurred_at': timezone.now().isoformat(), 'notes': 'Synthetic payment',
                'operation_key': str(uuid.uuid4()), 'expected_version': self.form['expected_version']})
            self.assertEqual(response.status_code, 200, response.content)
            self.form['expected_version'] += 1
            self.assertEqual(self.booking(amount_to_collect=999999).status_code, 200)
            self.assertEqual(book.call_args.args[0]['amount_to_collect'], expected)
            Shipment.objects.all().delete()  # Test isolation for the second balance scenario.

    @patch.object(Pathao, 'token', return_value='token')
    @patch.object(Pathao, 'book')
    def test_modeladmin_hooks_and_permissions(self, book, token):
        self.client.force_login(self.staff)
        self.assertEqual(self.booking().status_code, 403)
        self.staff.user_permissions.set(Permission.objects.filter(content_type__app_label='sanjilas', codename__in=['view_order', 'change_order', 'view_courieraccount', 'add_shipment']))
        with patch.object(admin.site._registry[Shipment], 'has_add_permission', return_value=False):
            self.assertEqual(self.booking().status_code, 403)
        with patch.object(admin.site._registry[CourierAccount], 'get_queryset', return_value=CourierAccount.objects.none()):
            self.assertEqual(self.booking().status_code, 404)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(self.base).status_code, 403)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.owner)
        self.assertEqual(csrf.post(self.base+'book/', self.form).status_code, 403)
        book.assert_not_called()

    def test_tokens_persist_refresh_and_never_enter_control_forms(self):
        client = Pathao('sandbox')
        with patch.object(client, 'transport', return_value={'access_token': 'SECRET_ACCESS', 'refresh_token': 'SECRET_REFRESH', 'expires_in': 3600}) as transport:
            self.assertEqual(client.token(), 'SECRET_ACCESS')
            self.assertEqual(Pathao('sandbox').token(), 'SECRET_ACCESS')
            transport.assert_called_once()
            CourierToken.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
            client.token()
            self.assertEqual(transport.call_args.args[2]['grant_type'], 'refresh_token')
        row = CourierToken.objects.get()
        response = self.client.get(f'/api/control/models/sanjilas/couriertoken/{row.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('SECRET_', response.content.decode())
        self.assertEqual(self.client.get('/api/control/models/sanjilas/couriertoken/export/').status_code, 403)

    @patch.object(Pathao, 'info')
    def test_reconciliation_checks_merchant_reference(self, info):
        row = Shipment.objects.create(order=self.order, account=self.account, environment='sandbox', state='uncertain', merchant_order_id='expected-reference', actor=self.owner)
        url = self.base+f'{row.pk}/refresh/'
        info.return_value = {'data': {'consignment_id': 'TEST-1', 'merchant_order_id': 'wrong'}}
        self.assertEqual(self.client.post(url, {'consignment_id': 'TEST-1'}).status_code, 400)
        info.return_value = {'data': {'consignment_id': 'TEST-1', 'merchant_order_id': row.merchant_order_id, 'order_status': 'Pending'}}
        self.assertEqual(self.client.post(url, {'consignment_id': 'TEST-1'}).status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.state, 'booked')

    def test_live_is_opt_in_and_freezes_cancellation(self):
        with self.assertRaises(ValidationError):
            Pathao('live')
        Shipment.objects.create(order=self.order, account=self.account, environment='live', state='uncertain', merchant_order_id='live-test', actor=self.owner)
        with self.assertRaises(ValidationError):
            transition_order(self.order.pk, 'cancelled')


@override_settings(PATHAO={'sandbox': CREDENTIALS, 'live': CREDENTIALS}, PATHAO_LIVE_ENABLED=False)
class CourierConcurrencyTests(TransactionTestCase):
    setUp = CourierTests.setUp

    @patch.object(Pathao, 'token', return_value='token')
    def test_concurrent_booking_sees_committed_reservation(self, token):
        entered, release = Event(), Event()

        def provider(payload):
            entered.set()
            if not release.wait(10):
                raise RuntimeError('Test did not release provider')
            return {'data': {'consignment_id': 'CONCURRENT-1', 'delivery_fee': 80}}

        def first_request():
            try:
                client = Client()
                client.force_login(self.owner)
                return client.post(self.base+'book/', self.form).status_code
            finally:
                connections.close_all()

        with patch.object(Pathao, 'book', side_effect=provider) as book, ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(first_request)
            try:
                self.assertTrue(entered.wait(10), 'First booking did not reach provider')
                self.assertEqual(Shipment.objects.get().state, 'submitting')
                self.assertEqual(self.client.post(self.base+'book/', self.form).status_code, 400)
            finally:
                release.set()
            self.assertEqual(first.result(timeout=10), 200)
            book.assert_called_once()
        self.assertEqual(Shipment.objects.count(), 1)

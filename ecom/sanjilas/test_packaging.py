from unittest.mock import patch
from django.contrib import admin
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from .commerce import transition_order
from .couriers import Pathao
from .courier_webhooks import process_one
from .models import CourierEvent, PackagingTask, Shipment, SiteSettings
from .test_couriers import CourierTests, CREDENTIALS


WEBHOOK = {'sandbox':{'url_token':'private-url', 'signature_secret':'private-signature', 'integration_secret':'integration-response'},
           'live':{'url_token':'private-url', 'signature_secret':'private-signature', 'integration_secret':'integration-response'}}


@override_settings(PATHAO={'sandbox':CREDENTIALS, 'live':CREDENTIALS}, PATHAO_LIVE_ENABLED=True, PATHAO_WEBHOOK=WEBHOOK)
class PackagingTests(TestCase):
    setUp = CourierTests.setUp

    def processing(self):
        transition_order(self.order.pk, 'processing', actor=self.owner)
        self.order.refresh_from_db()
        self.form['expected_version'] = self.order.revision
        self.pack_base = f'/api/control/operations/packaging/{self.order.pk}/'

    def pack(self):
        return self.client.post(self.pack_base+'pack/', {'expected_version':self.order.revision, 'item_weight':'.5', 'item_quantity':1})

    def shipment(self, environment='live', state='booked'):
        self.account.environment = environment
        self.account.save()
        return Shipment.objects.create(order=self.order, account=self.account, environment=environment, state=state,
            merchant_order_id='merchant-test', consignment_id='CONSIGNMENT-1', actor=self.owner,
            request_payload={'recipient_name':'Snapshot Recipient', 'recipient_phone':'01700000000', 'recipient_address':'Snapshot Address',
                             'amount_to_collect':int(self.order.total), 'item_weight':.5, 'item_quantity':1})

    def callback(self, row, **changes):
        body = {'event':'order.delivered', 'merchant_order_id':row.merchant_order_id, 'consignment_id':row.consignment_id, **changes}
        return self.client.post(f'/api/couriers/pathao/webhook/{row.environment}/private-url/', body, content_type='application/json', HTTP_X_PATHAO_SIGNATURE='private-signature')

    def test_processing_enqueues_exactly_once(self):
        self.processing()
        transition_order(self.order.pk, 'processing', actor=self.owner)
        self.assertEqual(PackagingTask.objects.filter(order=self.order).count(), 1)
        rows = self.client.get('/api/control/operations/packaging/').json()['rows']
        self.assertEqual(rows[0]['order_id'], str(self.order.pk))
        self.assertEqual(self.client.get(self.pack_base).status_code, 200)

    @patch.object(Pathao, 'token', return_value='token')
    @patch.object(Pathao, 'book', return_value={'data':{'consignment_id':'PACK-1', 'delivery_fee':80}})
    def test_pack_before_booking_and_match_weight(self, book, token):
        self.processing()
        self.assertEqual(self.client.post(self.base+'book/', self.form).status_code, 400)
        self.assertEqual(self.pack().status_code, 200)
        self.assertEqual(self.client.post(self.base+'book/', {**self.form, 'item_weight':1}).status_code, 400)
        self.assertEqual(self.client.post(self.base+'book/', self.form).status_code, 200)
        book.assert_called_once()

    def test_pack_and_handover_are_permission_and_csrf_checked(self):
        self.processing()
        with patch.object(admin.site._registry[PackagingTask], 'has_change_permission', return_value=False):
            self.assertEqual(self.pack().status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/api/control/operations/packaging/').status_code, 403)
        self.assertEqual(self.client.get(self.pack_base).status_code, 403)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.owner)
        self.assertEqual(csrf.post(self.pack_base+'pack/', {}).status_code, 403)

    def test_invoice_revision_requires_repacking(self):
        self.processing()
        self.pack()
        from .models import Order
        Order.objects.filter(pk=self.order.pk).update(revision=self.order.revision+1)
        self.order.refresh_from_db()
        self.assertEqual(self.client.post(self.pack_base+'handover/', {'shipment':self.shipment().pk}).status_code, 400)

    def test_handover_changes_order_once_and_keeps_inventory(self):
        self.processing()
        self.assertEqual(self.pack().status_code, 200)
        row = self.shipment()
        response = self.client.post(self.pack_base+'handover/', {'shipment':row.pk})
        self.assertEqual(response.status_code, 200, response.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'shipped')
        self.assertEqual(self.order.packaging_task.state, 'handed_over')
        self.assertEqual(self.client.post(self.pack_base+'handover/', {'shipment':row.pk}).status_code, 400)

    def test_sandbox_handover_does_not_ship_real_order(self):
        self.processing()
        self.pack()
        row = self.shipment('sandbox')
        self.assertEqual(self.client.post(self.pack_base+'handover/', {'shipment':row.pk}).status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'processing')

    def test_label_uses_booking_snapshot_without_tracking(self):
        self.processing()
        row = self.shipment()
        response = self.client.get(f'/api/control/parcel-label/{row.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['shipment']['recipient_name'], 'Snapshot Recipient')
        self.assertEqual([item['key'] for item in response.json()['formats']],['small','sticker','large'])
        self.assertEqual(response.json()['shipment']['account'],self.account.name)
        self.assertNotIn('(Live)',response.json()['shipment']['account'])
        self.assertNotIn('checkout_ip', response.content.decode())
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(f'/api/control/parcel-label/{row.pk}/').status_code, 403)

    def test_courier_name_is_exact_and_label_uses_site_sender_without_tracking(self):
        self.account.name='Pathao';self.account.save()
        self.assertEqual(str(self.account),'Pathao')
        site=SiteSettings.load();site.site_name='Our shop';site.invoice_address='Our pickup address';site.invoice_phone='01700000000';site.save()
        self.processing();row=self.shipment()
        row.request_payload['checkout_ip']='192.0.2.1';row.request_payload['browser_key']='private';row.save()
        data=self.client.get(f'/api/control/parcel-label/{row.pk}/').json()
        self.assertEqual(data['shipment']['account'],'Pathao')
        self.assertEqual(data['sender'],{'name':'Our shop','address':'Our pickup address','phone':'01700000000'})
        self.assertNotIn('checkout_ip',data['shipment']);self.assertNotIn('browser_key',data['shipment'])

    def test_cancellation_removes_task_from_queue(self):
        self.processing()
        transition_order(self.order.pk, 'cancelled', actor=self.owner)
        self.assertEqual(self.client.get('/api/control/operations/packaging/').json()['count'], 0)
        self.assertEqual(PackagingTask.objects.get(order=self.order).state, 'cancelled')

    def test_webhook_auth_handshake_and_deduplication(self):
        self.processing()
        row = self.shipment()
        url = '/api/couriers/pathao/webhook/live/private-url/'
        self.assertEqual(self.client.post(url, {}, content_type='application/json').status_code, 403)
        handshake = self.client.post(url, {'event':'webhook_integration'}, content_type='application/json', HTTP_X_PATHAO_SIGNATURE='private-signature')
        self.assertEqual(handshake.status_code, 202)
        self.assertEqual(handshake['X-Pathao-Merchant-Webhook-Integration-Secret'], 'integration-response')
        self.assertEqual(self.callback(row).status_code, 202)
        self.assertEqual(self.callback(row).status_code, 202)
        self.assertEqual(CourierEvent.objects.count(), 1)
        self.assertEqual(self.callback(row, consignment_id='wrong').status_code, 404)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'processing')

    @override_settings(PATHAO_WEBHOOK={'live':{'signature_secret':'merchant-secret'}})
    def test_public_callback_matches_merchant_panel_and_requires_only_signature(self):
        from .courier_webhooks import INTEGRATION_RESPONSE
        url='/shipping/api/webhook/pathao/'
        client=Client(enforce_csrf_checks=True)
        body={'event':'webhook_integration'}
        self.assertEqual(client.head(url).status_code,405)
        self.assertEqual(client.post(url,body,content_type='application/json').status_code,403)
        self.assertEqual(client.post(url,body,content_type='application/json',HTTP_X_PATHAO_SIGNATURE='wrong').status_code,403)
        response=client.post(url,body,content_type='application/json',HTTP_X_PATHAO_SIGNATURE='merchant-secret')
        self.assertEqual(response.status_code,202)
        self.assertEqual(response['X-Pathao-Merchant-Webhook-Integration-Secret'],INTEGRATION_RESPONSE)

    @override_settings(PATHAO_WEBHOOK={'live':{'signature_secret':'merchant-secret'}})
    def test_public_callback_persists_shipment_event_without_changing_status_directly(self):
        self.processing()
        row=self.shipment()
        response=self.client.post('/shipping/api/webhook/pathao/',{'event':'order.delivered',
            'merchant_order_id':row.merchant_order_id,'consignment_id':row.consignment_id},
            content_type='application/json',HTTP_X_PATHAO_SIGNATURE='merchant-secret')
        self.assertEqual(response.status_code,202)
        self.assertEqual(CourierEvent.objects.get().shipment_id,row.pk)
        self.order.refresh_from_db();self.assertEqual(self.order.status,'processing')

    @override_settings(PATHAO_WEBHOOK={'live':{'signature_secret':''}})
    def test_public_callback_stays_closed_without_server_secret(self):
        self.assertEqual(self.client.post('/shipping/api/webhook/pathao/',{'event':'webhook_integration'},
            content_type='application/json',HTTP_X_PATHAO_SIGNATURE='').status_code,403)

    @patch.object(Pathao, 'info')
    def test_webhook_verifies_current_state_then_completes_without_recording_payment(self, info):
        self.processing()
        row = self.shipment()
        self.callback(row)
        info.return_value = {'data':{'consignment_id':row.consignment_id, 'merchant_order_id':row.merchant_order_id, 'order_status_slug':'Delivered'}}
        self.assertTrue(process_one())
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'completed')
        self.assertEqual(self.order.payment_status, 'unpaid')
        self.assertIsNotNone(CourierEvent.objects.get().processed_at)
        self.assertFalse(process_one())

    @patch.object(Pathao, 'info')
    def test_untrusted_delivered_event_cannot_override_provider_status(self, info):
        self.processing()
        row = self.shipment()
        self.callback(row)
        info.return_value = {'data':{'consignment_id':row.consignment_id, 'merchant_order_id':row.merchant_order_id, 'order_status_slug':'Pending'}}
        process_one()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'processing')

    @patch.object(Pathao, 'info', side_effect=TimeoutError)
    def test_failed_verification_retries_without_order_changes(self, info):
        self.processing()
        row = self.shipment()
        self.callback(row)
        process_one()
        event = CourierEvent.objects.get()
        self.assertIsNone(event.processed_at)
        self.assertGreater(event.next_attempt_at, timezone.now())
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'processing')

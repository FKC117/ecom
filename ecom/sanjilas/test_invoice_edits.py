import json,uuid
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from .models import Product,ProductVariant,Collection,Order,InvoiceRevision,InventoryMovement,SiteSettings
from .commerce import set_item,place_order,transition_order

ROOT='/api/control/invoices/'

class InvoiceEditTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_superuser('edit-owner')
        self.customer=get_user_model().objects.create_user('edit-customer')
        collection=Collection.objects.create(name='Rings',slug='rings')
        self.product=Product.objects.create(name='Ring',slug='ring',collection=collection,price=100,stock_quantity=5)
        SiteSettings.objects.create()
        set_item(self.customer,self.product.pk,None,1)
        self.order=place_order(self.customer,uuid.uuid4(),{'customer_name':'Customer','email':'preview@example.com','phone':'01000000000','address':'Address','city':'Dhaka','postal_code':'','notes':''})
        self.client.force_login(self.owner)

    def payload(self,qty=1):
        return {'checkout_key':str(uuid.uuid4()),'expected_version':self.order.revision,'edit_reason':'Correct customer request','customer_name':'Updated customer','shipping_fee':'10',
                'items':json.dumps([{'model':'product','id':self.product.pk,'invoice_name':'Invoice ring','sku':'INV-RING','regular_price':'120','discount_type':'fixed','discount':'20','quantity':qty}])}

    def reviewed(self,payload):
        response=self.client.post(ROOT+f'{self.order.pk}/preview/',payload)
        self.assertEqual(response.status_code,200,response.content)
        return {**payload,'quote':response.json()['quote']}

    def test_preview_does_not_mutate_stock_and_save_records_difference_and_history(self):
        values=self.reviewed(self.payload(3))
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,4)
        self.assertFalse(InvoiceRevision.objects.exists())
        response=self.client.post(ROOT+f'{self.order.pk}/save/',values)
        self.assertEqual(response.status_code,200,response.content)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,2)
        self.order.refresh_from_db();self.assertEqual(self.order.total,310)
        self.assertEqual(self.order.revision,2)
        revision=InvoiceRevision.objects.get()
        self.assertEqual(revision.before['items'][0]['quantity'],1)
        self.assertEqual(revision.after['items'][0]['quantity'],3)
        self.assertEqual(revision.actor_id,self.owner.pk)
        self.assertEqual(revision.reason,'Correct customer request')
        self.assertEqual(self.client.post(ROOT+f'{self.order.pk}/save/',values).status_code,200)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,2)
        self.assertEqual(InvoiceRevision.objects.count(),1)
        transition_order(self.order.pk,'cancelled',actor=self.owner)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,5)
        self.assertEqual(InvoiceRevision.objects.count(),2)

    def test_other_cart_reservations_are_preserved(self):
        other=get_user_model().objects.create_user('holding-customer')
        set_item(other,self.product.pk,None,2)
        response=self.client.post(ROOT+f'{self.order.pk}/preview/',self.payload(4))
        self.assertEqual(response.status_code,400)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,4)
        self.assertEqual(self.order.items.get().quantity,1)

    def test_stale_edit_and_missing_reason_cannot_write(self):
        values=self.reviewed(self.payload())
        transition_order(self.order.pk,'processing',actor=self.owner)
        self.assertEqual(self.client.post(ROOT+f'{self.order.pk}/save/',values).status_code,400)
        values=self.payload();values['edit_reason']=''
        self.assertEqual(self.client.post(ROOT+f'{self.order.pk}/preview/',values).status_code,400)

    def test_custom_item_and_price_only_changes_do_not_change_catalog_stock(self):
        values=self.payload()
        lines=json.loads(values['items']);lines.append({'model':'custom','name':'Repair','price':'50','discount':'5','quantity':1})
        values['items']=json.dumps(lines)
        values=self.reviewed(values)
        self.assertEqual(self.client.post(ROOT+f'{self.order.pk}/save/',values).status_code,200)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,4)
        self.assertEqual(self.order.items.count(),2)
        self.assertEqual(self.order.items.get(product=self.product).product_name,'Invoice ring')
        self.assertEqual(self.order.items.get(product=self.product).sku,'INV-RING')

    def test_customer_is_denied_and_history_is_read_only(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(ROOT+f'{self.order.pk}/edit/').status_code,403)
        self.assertEqual(self.client.get(ROOT+f'{self.order.pk}/history/').status_code,403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post('/api/control/models/sanjilas/invoicerevision/new/',{}).status_code,403)

    def test_order_breakdown_shows_regular_discount_and_net(self):
        data=self.client.get(f'/api/control/operations/orders/{self.order.pk}/').json()
        self.assertEqual(data['regular_subtotal'],'100.00')
        self.assertEqual(data['discount_total'],'0.00')
        self.assertEqual(data['items'][0]['regular_price'],'100.00')
        self.assertEqual(data['items'][0]['discount'],'0.00')

    def test_switching_to_a_variant_returns_old_stock_and_deducts_new_stock(self):
        parent=Product.objects.create(name='Variant ring',slug='variant-ring',collection=self.product.collection,price=200)
        variant=ProductVariant.objects.create(product=parent,name='Size 7',sku='V-7',stock_quantity=4)
        values=self.payload()
        values['items']=json.dumps([{'model':'productvariant','id':variant.pk,'regular_price':'200','discount_type':'fixed','discount':'0','quantity':2}])
        values=self.reviewed(values)
        self.assertEqual(self.client.post(ROOT+f'{self.order.pk}/save/',values).status_code,200)
        self.product.refresh_from_db();variant.refresh_from_db()
        self.assertEqual((self.product.stock_quantity,variant.stock_quantity),(5,2))

    def test_cancelled_invoice_edits_never_change_stock(self):
        transition_order(self.order.pk,'cancelled',actor=self.owner)
        self.order.refresh_from_db();self.product.refresh_from_db()
        self.product.stock_quantity=0;self.product.save()
        values=self.reviewed(self.payload(3))
        self.assertEqual(self.client.post(ROOT+f'{self.order.pk}/save/',values).status_code,200)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,0)

    def test_amend_permission_is_separate_from_order_processing(self):
        from django.contrib.auth.models import Permission
        staff=get_user_model().objects.create_user('invoice-editor',is_staff=True)
        staff.user_permissions.set(Permission.objects.filter(content_type__app_label='sanjilas',codename__in=['change_order','view_orderitem','view_product']))
        self.client.force_login(staff)
        self.assertEqual(self.client.get(ROOT+f'{self.order.pk}/edit/').status_code,403)
        staff.user_permissions.add(Permission.objects.get(content_type__app_label='sanjilas',codename='edit_invoice'))
        self.assertEqual(self.client.get(ROOT+f'{self.order.pk}/edit/').status_code,200)
        self.assertEqual(self.client.get('/api/control/manual-invoices/catalog/').status_code,200)

    def test_percentage_discount_type_and_value_survive_reopening_and_history(self):
        values=self.payload()
        lines=json.loads(values['items']);lines[0]['discount_type']='percent';lines[0]['discount']='20'
        values['items']=json.dumps(lines);values=self.reviewed(values)
        self.assertEqual(self.client.post(ROOT+f'{self.order.pk}/save/',values).status_code,200)
        loaded=self.client.get(ROOT+f'{self.order.pk}/edit/').json()
        self.assertEqual(loaded['items'][0]['discount_type'],'percent')
        self.assertEqual(loaded['items'][0]['discount'],'20.00')
        recorded=InvoiceRevision.objects.get().after['items'][0]
        self.assertEqual(recorded['discount_mode'],'percent')
        self.assertEqual(recorded['discount_input'],'20.00')

    def test_history_cannot_be_overwritten_or_deleted(self):
        values=self.reviewed(self.payload())
        self.client.post(ROOT+f'{self.order.pk}/save/',values)
        row=InvoiceRevision.objects.get()
        row.reason='Rewritten'
        with self.assertRaises(ValidationError):row.save()
        with self.assertRaises(ValidationError):row.delete()

    def test_payments_partial_full_refund_are_audited_and_idempotent(self):
        from django.utils import timezone
        from .models import OrderPayment
        from .payments import summary
        url=f'/api/control/operations/orders/{self.order.pk}/payments/'
        def payload(amount,version,kind='payment'):
            return {'amount':amount,'kind':kind,'method':'cash','notes':'Cash received or returned','occurred_at':timezone.now().isoformat(),'expected_version':version,'operation_key':str(uuid.uuid4())}
        values=payload(40,1)
        response=self.client.post(url,values);self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['payment_status'],'partial');self.assertEqual(response.json()['amount_due'],'60.00')
        self.assertEqual(self.client.post(url,values).status_code,200)
        self.assertEqual(OrderPayment.objects.count(),1)
        self.assertEqual(self.client.post(url,payload(70,2)).status_code,400)
        self.assertEqual(self.client.post(url,payload(60,1)).status_code,400)
        response=self.client.post(url,payload(60,2));self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['payment_status'],'paid')
        self.order.refresh_from_db();self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,4)
        self.assertEqual(InvoiceRevision.objects.count(),2)
        transition_order(self.order.pk,'cancelled',actor=self.owner)
        self.order.refresh_from_db();self.assertEqual(summary(self.order)['refund_due'],100)
        self.assertEqual(self.client.post(url,payload(101,4,'refund')).status_code,400)
        response=self.client.post(url,payload(100,4,'refund'));self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['refund_due'],'0.00')
        row=OrderPayment.objects.first()
        with self.assertRaises(ValidationError):row.save()
        with self.assertRaises(ValidationError):row.delete()
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(url,payload(1,5)).status_code,403)

    def test_invoice_reduction_retains_payment_and_shows_refund_due(self):
        from django.utils import timezone
        from .payments import summary
        url=f'/api/control/operations/orders/{self.order.pk}/payments/'
        response=self.client.post(url,{'amount':100,'kind':'payment','method':'bank','notes':'Advance received','occurred_at':timezone.now().isoformat(),'expected_version':1,'operation_key':str(uuid.uuid4())})
        self.assertEqual(response.status_code,200,response.content)
        self.order.refresh_from_db()
        values=self.payload();values['shipping_fee']='0'
        lines=json.loads(values['items']);lines[0]['regular_price']='80';lines[0]['discount']='0';values['items']=json.dumps(lines)
        values=self.reviewed(values)
        self.assertEqual(self.client.post(ROOT+f'{self.order.pk}/save/',values).status_code,200)
        self.order.refresh_from_db();balances=summary(self.order)
        self.assertEqual(balances['refund_due'],20);self.assertEqual(balances['net_paid'],100)
        invoice=self.client.get(f'/api/shop/orders/{self.order.pk}/invoice/').json()['order']
        self.assertEqual(invoice['refund_due'],'20.00');self.assertEqual(len(invoice['payments']),1)

    def test_delivery_rate_is_server_owned_and_preserved_in_history(self):
        site=SiteSettings.load();site.delivery_inside_dhaka=60;site.delivery_outside_dhaka=120;site.save()
        values=self.payload();values['delivery_zone']='outside';values['shipping_fee']='1'
        values=self.reviewed(values)
        response=self.client.post(ROOT+f'{self.order.pk}/save/',values)
        self.assertEqual(response.status_code,200,response.content)
        self.order.refresh_from_db();self.assertEqual(self.order.shipping_fee,120)
        self.assertEqual(self.order.delivery_zone,'outside')
        self.assertEqual(InvoiceRevision.objects.get().after['delivery_zone'],'outside')

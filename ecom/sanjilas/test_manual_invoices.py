import json,uuid
from unittest.mock import patch
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.admin.models import LogEntry
from django.test import TestCase,Client
from .models import Product,Collection,Order,OrderItem,InventoryMovement,SiteSettings
from .commerce import set_item,transition_order

ROOT='/api/control/manual-invoices/'

class ManualInvoiceTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_superuser('manual-owner')
        self.customer=get_user_model().objects.create_user('manual-customer')
        self.client.force_login(self.owner)
        collection=Collection.objects.create(name='Rings',slug='rings')
        self.product=Product.objects.create(name='Ring',slug='ring',collection=collection,price=100,stock_quantity=3)
        SiteSettings.objects.create()

    def payload(self,lines=None):
        return {'checkout_key':str(uuid.uuid4()),'customer_name':'Counter customer','shipping_fee':'50','items':json.dumps(lines if lines is not None else [
            {'model':'product','id':self.product.pk,'quantity':1,'price':'0'},
            {'model':'custom','name':'Custom jewellery repair','sku':'REPAIR','price':'500','discount':'50','quantity':2}])}

    def reviewed(self,values):
        response=self.client.post(ROOT+'preview/',values)
        self.assertEqual(response.status_code,200,response.content)
        return {**values,'quote':response.json()['quote']}

    def test_catalog_and_custom_invoice_totals_stock_and_audit(self):
        values=self.reviewed(self.payload())
        response=self.client.post(ROOT+'issue/',values)
        self.assertEqual(response.status_code,200,response.content)
        order=Order.objects.get(pk=response.json()['id'])
        self.assertIsNone(order.user_id)
        self.assertEqual(order.created_by_id,self.owner.pk)
        self.assertEqual(order.source,'manual')
        self.assertEqual(order.total,1050)
        self.assertEqual(order.items.get(product__isnull=True).line_total,900)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,2)
        self.assertEqual(InventoryMovement.objects.filter(reason='sale',actor=self.owner).count(),1)
        self.assertTrue(LogEntry.objects.filter(object_id=str(order.pk),action_flag=1).exists())
        invoice=self.client.get(f'/api/shop/orders/{order.pk}/invoice/').json()['order']
        self.assertEqual(invoice['total'],'1050.00')
        self.assertEqual(len(invoice['items']),2)
        transition_order(order.pk,'cancelled',actor=self.owner)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,3)
        self.assertEqual(InventoryMovement.objects.filter(reason='cancellation').count(),1)

    def test_preview_has_no_stock_or_order_side_effects_and_retry_is_idempotent(self):
        values=self.reviewed(self.payload())
        self.assertFalse(Order.objects.exists())
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,3)
        first=self.client.post(ROOT+'issue/',values).json()
        second=self.client.post(ROOT+'issue/',values).json()
        self.assertEqual(first,second)
        self.assertEqual(Order.objects.count(),1)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,2)

    def test_existing_cart_holds_cannot_be_taken_by_manual_invoice(self):
        set_item(self.customer,self.product.pk,None,3)
        response=self.client.post(ROOT+'preview/',self.payload())
        self.assertEqual(response.status_code,400)
        self.assertFalse(Order.objects.exists())

    def test_invalid_custom_prices_and_duplicate_catalog_lines_are_rejected(self):
        for line in [
            {'model':'custom','name':'Bad','price':'-1','discount':'0','quantity':1},
            {'model':'custom','name':'Bad','price':'10','discount':'11','quantity':1},
            {'model':'custom','name':'Bad','price':'10.999','quantity':1},
            {'model':'product','id':self.product.pk,'quantity':0}]:
            self.assertEqual(self.client.post(ROOT+'preview/',self.payload([line])).status_code,400)
        line={'model':'product','id':self.product.pk,'quantity':1}
        self.assertEqual(self.client.post(ROOT+'preview/',self.payload([line,line])).status_code,400)

    def test_review_detects_changed_catalog_price(self):
        values=self.reviewed(self.payload())
        self.product.price=200;self.product.save()
        self.assertEqual(self.client.post(ROOT+'issue/',values).status_code,400)
        self.assertFalse(Order.objects.exists())
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,3)

    def test_manual_permission_and_registered_queryset_are_required(self):
        staff=get_user_model().objects.create_user('manual-staff',is_staff=True)
        staff.user_permissions.set(Permission.objects.filter(content_type__app_label='sanjilas',codename__in=['change_order','view_orderitem','view_product']))
        self.client.force_login(staff)
        self.assertEqual(self.client.post(ROOT+'preview/',self.payload()).status_code,403)
        staff.user_permissions.add(Permission.objects.get(content_type__app_label='sanjilas',codename='create_manual_invoice'))
        self.assertEqual(self.client.post(ROOT+'preview/',self.payload()).status_code,200)
        ma=admin.site._registry[Product]
        with patch.object(ma,'get_queryset',return_value=Product.objects.none()):
            self.assertEqual(self.client.post(ROOT+'preview/',self.payload()).status_code,403)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(ROOT+'preview/',self.payload()).status_code,403)

    def test_csrf_is_required(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.owner)
        self.assertEqual(client.post(ROOT+'issue/',self.payload()).status_code,403)

    def test_catalog_discount_override_and_percentage_custom_discount(self):
        values=self.payload([
            {'model':'product','id':self.product.pk,'quantity':1,'discount_type':'percent','discount':'20'},
            {'model':'custom','name':'Gift box','quantity':2,'price':'50','discount_type':'percent','discount':'10'},
        ])
        response=self.client.post(ROOT+'preview/',values)
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['subtotal'],'170.00')
        self.assertEqual(response.json()['discount_total'],'30.00')
        values['quote']=response.json()['quote']
        issued=self.client.post(ROOT+'issue/',values)
        self.assertEqual(issued.status_code,200)
        order=Order.objects.get(pk=issued.json()['id'])
        self.assertEqual(order.items.get(product=self.product).unit_price,80)

    def test_catalog_discount_replaces_instead_of_stacking_catalog_sale(self):
        self.product.discount_type='percent';self.product.discount_value=10;self.product.save()
        values=self.payload([{'model':'product','id':self.product.pk,'quantity':1,'discount_type':'fixed','discount':'25'}])
        response=self.client.post(ROOT+'preview/',values)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['subtotal'],'75.00')
        for kind,value in [('percent','101'),('fixed','101'),('percent','-1')]:
            values=self.payload([{'model':'product','id':self.product.pk,'quantity':1,'discount_type':kind,'discount':value}])
            self.assertEqual(self.client.post(ROOT+'preview/',values).status_code,400)

    def test_manual_percentage_rounding_matches_catalog_prices(self):
        values=self.payload([{'model':'custom','name':'Rounding check','quantity':1,'price':'0.05','discount_type':'percent','discount':'10'}])
        response=self.client.post(ROOT+'preview/',values)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['subtotal'],'0.05')


    def test_initial_advance_is_reviewed_and_saved_atomically_once(self):
        from django.utils import timezone
        from .models import OrderPayment
        values=self.payload()
        values.update(amount_paid='300',payment_method='bkash',payment_reference='ADV-TEST',payment_date=timezone.now().isoformat(),payment_notes='Advance received')
        preview=self.client.post(ROOT+'preview/',values)
        self.assertEqual(preview.status_code,200,preview.content)
        self.assertEqual(preview.json()['amount_paid'],'300');self.assertEqual(preview.json()['amount_due'],'750.00')
        self.assertFalse(OrderPayment.objects.exists())
        values['quote']=preview.json()['quote']
        response=self.client.post(ROOT+'issue/',values);self.assertEqual(response.status_code,200,response.content)
        order=Order.objects.get();payment=OrderPayment.objects.get()
        self.assertEqual(payment.amount,300);self.assertEqual(payment.method,'bkash');self.assertEqual(payment.actor,self.owner)
        self.assertEqual(order.payment_status,'partial')
        self.assertEqual(self.client.post(ROOT+'issue/',values).status_code,200)
        self.assertEqual(OrderPayment.objects.count(),1)
        data=self.client.get(f'/api/shop/orders/{order.pk}/invoice/').json()['order']
        self.assertEqual(data['amount_due'],'750.00')

    def test_full_advance_and_invalid_or_changed_advance(self):
        from django.utils import timezone
        values=self.payload();values.update(amount_paid='1050',payment_method='cash',payment_date=timezone.now().isoformat())
        values=self.reviewed(values)
        changed={**values,'amount_paid':'100'}
        self.assertEqual(self.client.post(ROOT+'issue/',changed).status_code,400)
        self.assertFalse(Order.objects.exists());self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,3)
        self.assertEqual(self.client.post(ROOT+'preview/',{**values,'amount_paid':'1051'}).status_code,400)
        self.assertEqual(self.client.post(ROOT+'preview/',{**values,'amount_paid':'-1'}).status_code,400)
        response=self.client.post(ROOT+'issue/',values);self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(Order.objects.get().payment_status,'paid')

    def test_advance_requires_payment_permission(self):
        from django.utils import timezone
        staff=get_user_model().objects.create_user('issuer-without-payment',is_staff=True)
        staff.user_permissions.set(Permission.objects.filter(content_type__app_label='sanjilas',codename__in=['create_manual_invoice','change_order','view_orderitem','view_product']))
        self.client.force_login(staff)
        values=self.payload();values.update(amount_paid='50',payment_method='cash',payment_date=timezone.now().isoformat())
        self.assertEqual(self.client.post(ROOT+'preview/',values).status_code,403)
        self.assertFalse(Order.objects.exists())

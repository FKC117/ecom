from unittest.mock import patch
import uuid

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase,Client

from .commerce import set_item,place_order
from .models import Product,ProductVariant,Category,InventoryMovement,Order,SiteSettings


class OperationsTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_superuser('ops-owner')
        self.staff=get_user_model().objects.create_user('ops-staff',is_staff=True)
        self.customer=get_user_model().objects.create_user('ops-customer')
        category=Category.objects.create(name='Rings',slug='rings')
        self.product=Product.objects.create(name='Ring',slug='ring',category=category,price=100,stock_quantity=10)
        parent=Product.objects.create(name='Variant ring',slug='variant-ring',category=category,price=200,stock_quantity=99)
        self.variant=ProductVariant.objects.create(product=parent,name='Size 7',sku='SIZE-7',stock_quantity=3)
        SiteSettings.objects.create()
        self.client.force_login(self.owner)

    def grant(self,*codes):
        self.staff.user_permissions.set(Permission.objects.filter(content_type__app_label='sanjilas',codename__in=codes))
        self.client.force_login(self.staff)

    def order(self):
        set_item(self.customer,self.product.pk,None,1)
        return place_order(self.customer,uuid.uuid4(),{'customer_name':'Preview Customer','email':'preview@example.com','phone':'01000000000','address':'Test address','city':'Dhaka','postal_code':'','notes':''})

    def test_stock_counts_holds_without_double_counting_variant_parent(self):
        set_item(self.customer,self.product.pk,None,2)
        response=self.client.get('/api/control/operations/stock/').json()
        self.assertEqual(response['summary'],{'on_hand':13,'reserved':2,'available':11,'low':1})
        self.assertEqual(response['count'],2)
        response=self.client.get('/api/control/operations/stock/?state=low').json()
        self.assertEqual(response['rows'][0]['sku'],'SIZE-7')

    def test_adjustment_records_reason_actor_and_audit(self):
        response=self.client.post(f'/api/control/operations/stock/product/{self.product.pk}/adjust/',{'delta':5,'expected':10,'note':'New delivery received'})
        self.assertEqual(response.status_code,200,response.content)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,15)
        movement=InventoryMovement.objects.filter(product=self.product).first()
        self.assertEqual((movement.quantity,movement.actor_id,movement.note),(5,self.owner.pk,'New delivery received'))
        self.assertTrue(LogEntry.objects.filter(user=self.owner,object_id=str(self.product.pk)).exists())

    def test_adjustment_cannot_break_reservations_or_overwrite_new_stock(self):
        set_item(self.customer,self.product.pk,None,2)
        url=f'/api/control/operations/stock/product/{self.product.pk}/adjust/'
        self.assertEqual(self.client.post(url,{'delta':-9,'expected':10,'note':'Damaged'}).status_code,400)
        self.assertEqual(self.client.post(url,{'delta':1,'expected':9,'note':'Delivery'}).status_code,409)
        self.assertEqual(self.client.post(url,{'delta':1,'expected':10,'note':''}).status_code,400)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,10)

    def test_permissions_apply_to_every_endpoint_and_workspaces(self):
        self.grant('view_product')
        session=self.client.get('/api/control/session/').json()
        self.assertEqual([row['key'] for row in session['workspaces']],['stock'])
        data=self.client.get('/api/control/operations/stock/').json()
        self.assertEqual(data['count'],1)
        self.assertFalse(data['rows'][0]['can_change'])
        self.assertEqual(self.client.get('/api/control/operations/orders/').status_code,403)
        self.assertEqual(self.client.post(f'/api/control/operations/stock/product/{self.product.pk}/adjust/',{'delta':1,'expected':10,'note':'Delivery'}).status_code,403)
        self.assertEqual(self.client.get(f'/api/control/operations/stock/product/{self.product.pk}/movements/').status_code,403)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get('/api/control/operations/stock/').status_code,403)
        self.client.logout();self.assertEqual(self.client.get('/api/control/operations/orders/').status_code,401)

    def test_queryset_and_readonly_hooks_remain_authoritative(self):
        ma=admin.site._registry[Product]
        with patch.object(ma,'get_queryset',return_value=Product.objects.none()):
            self.assertEqual(self.client.post(f'/api/control/operations/stock/product/{self.product.pk}/adjust/',{'delta':1,'expected':10,'note':'Delivery'}).status_code,404)
        with patch.object(ma,'get_readonly_fields',return_value=('stock_quantity',)):
            self.assertEqual(self.client.post(f'/api/control/operations/stock/product/{self.product.pk}/adjust/',{'delta':1,'expected':10,'note':'Delivery'}).status_code,403)

    def test_order_search_detail_and_processing(self):
        order=self.order()
        response=self.client.get('/api/control/operations/orders/',{'q':order.reference}).json()
        self.assertEqual(response['count'],1)
        detail=self.client.get(f'/api/control/operations/orders/{order.pk}/').json()
        self.assertEqual(detail['reference'],order.reference)
        self.assertEqual(detail['items'][0]['quantity'],1)
        self.assertEqual(detail['actions'],['processing','cancelled'])
        response=self.client.post(f'/api/control/models/sanjilas/order/{order.pk}/',{'status':'processing'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get('/api/control/operations/orders/?status=placed').json()['count'],0)

    @patch('sanjilas.couriers.Pathao.transport',side_effect=AssertionError('Orders must read saved courier status only'))
    def test_orders_show_latest_saved_courier_status_without_api_calls(self,transport):
        from .models import CourierAccount,Shipment
        from .commerce import transition_order
        order=self.order()
        transition_order(order.pk,'processing');transition_order(order.pk,'shipped')
        account=CourierAccount.objects.create(name='Pathao',environment='live',store_id=1)
        shipment=Shipment.objects.create(order=order,account=account,environment='live',state='booked',
            merchant_order_id='ops-live',consignment_id='TEST-OPS',courier_status='Received_at_Last_Mile_HUB',actor=self.owner)
        row=self.client.get('/api/control/operations/orders/').json()['rows'][0]
        self.assertEqual(row['status'],'shipped')
        self.assertEqual(row['courier']['account'],'Pathao')
        self.assertEqual(row['courier']['status'],'Received at Last Mile HUB')
        Shipment.objects.filter(pk=shipment.pk).update(courier_status='Assigned_for_Delivery')
        row=self.client.get('/api/control/operations/orders/').json()['rows'][0]
        self.assertEqual(row['courier']['status'],'Assigned for Delivery')
        transport.assert_not_called()

    def test_order_courier_summary_respects_permissions_and_prefers_live(self):
        from .models import CourierAccount,Shipment
        order=self.order()
        live=CourierAccount.objects.create(name='Real courier',environment='live',store_id=1)
        sandbox=CourierAccount.objects.create(name='Test courier',environment='sandbox',store_id=2)
        real=Shipment.objects.create(order=order,account=live,environment='live',state='booked',merchant_order_id='ops-real',courier_status='In_Transit',actor=self.owner)
        Shipment.objects.create(order=order,account=sandbox,environment='sandbox',state='booked',merchant_order_id='ops-test',courier_status='Delivered',actor=self.owner)
        endpoint='/api/control/operations/orders/'
        self.assertEqual(self.client.get(endpoint).json()['rows'][0]['courier']['account'],'Real courier')
        self.grant('view_order')
        self.assertIsNone(self.client.get(endpoint).json()['rows'][0]['courier'])
        self.client.force_login(self.owner)
        with patch.object(admin.site._registry[Shipment],'get_queryset',return_value=Shipment.objects.none()):
            self.assertIsNone(self.client.get(endpoint).json()['rows'][0]['courier'])
        with patch.object(admin.site._registry[Shipment],'has_view_or_change_permission',side_effect=lambda request,obj=None:obj is None or obj.pk!=real.pk):
            self.assertEqual(self.client.get(endpoint).json()['rows'][0]['courier']['environment'],'sandbox')
        with patch.object(admin.site._registry[CourierAccount],'get_queryset',return_value=CourierAccount.objects.none()):
            self.assertIsNone(self.client.get(endpoint).json()['rows'][0]['courier'])

    def test_stock_adjustment_requires_csrf(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.owner)
        self.assertEqual(client.post(f'/api/control/operations/stock/product/{self.product.pk}/adjust/',{'delta':1,'expected':10,'note':'Delivery'}).status_code,403)

from unittest.mock import patch
import uuid

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase,Client

from .commerce import set_item,place_order
from .models import Product,ProductVariant,Collection,InventoryMovement,Order,SiteSettings


class OperationsTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_superuser('ops-owner')
        self.staff=get_user_model().objects.create_user('ops-staff',is_staff=True)
        self.customer=get_user_model().objects.create_user('ops-customer')
        collection=Collection.objects.create(name='Rings',slug='rings')
        self.product=Product.objects.create(name='Ring',slug='ring',collection=collection,price=100,stock_quantity=10)
        parent=Product.objects.create(name='Variant ring',slug='variant-ring',collection=collection,price=200,stock_quantity=99)
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

    def test_stock_adjustment_requires_csrf(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.owner)
        self.assertEqual(client.post(f'/api/control/operations/stock/product/{self.product.pk}/adjust/',{'delta':1,'expected':10,'note':'Delivery'}).status_code,403)

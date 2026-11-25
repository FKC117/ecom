import json
import uuid
from unittest.mock import patch
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase,override_settings
from .commerce import set_item,place_order,transition_order
from .locations import resolve,map_published_directory,courier_destination
from .models import City,Zone,Area,Order,Product,Category,SiteSettings,CourierAccount,CourierLocation,CartItem,Cart
from .couriers import Pathao

CREDENTIALS={'client_id':'test','client_secret':'test','username':'test','password':'test'}

@override_settings(PATHAO={'sandbox':CREDENTIALS,'live':CREDENTIALS},PATHAO_LIVE_ENABLED=False)
class OrderAddressTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('address-customer')
        self.owner=get_user_model().objects.create_superuser('address-owner')
        SiteSettings.objects.create(order_protection_enabled=False)
        category=Category.objects.create(name='Address test',slug='address-test')
        self.product=Product.objects.create(name='Test item',slug='address-item',category=category,price=100,stock_quantity=10)
        self.city=City.objects.create(name='City A')
        self.zone=Zone.objects.create(city=self.city,name='Zone A')
        self.area=Area.objects.create(city=self.city,zone=self.zone,name='Area A')
        self.details={'customer_name':'Test Customer','phone':'01710000000','address':'House 1 Test Street','email':'','postal_code':'','notes':''}

    def order(self):
        set_item(self.user,self.product.pk,None,1)
        return place_order(self.user,uuid.uuid4(),{**self.details,**resolve(self.city.pk,self.area.pk,zone=self.zone.pk)})

    def test_hierarchy_validates_and_area_names_can_repeat_in_different_zones(self):
        other=Zone.objects.create(city=self.city,name='Zone B')
        other_area=Area.objects.create(city=self.city,zone=other,name='Area A')
        with self.assertRaises(ValidationError):resolve(self.city.pk,other_area.pk,zone=self.zone.pk)
        with self.assertRaises(ValidationError):resolve(self.city.pk,self.area.pk)
        self.assertEqual(resolve(self.city.pk,other_area.pk,zone=other.pk)['zone_record'],other)
        foreign=City.objects.create(name='City B')
        with self.assertRaises(ValidationError):resolve(foreign.pk,self.area.pk,zone=self.zone.pk)

    @patch.object(Pathao,'transport',side_effect=AssertionError('Address searches must use database only'))
    def test_public_search_scopes_city_zone_area(self,transport):
        other=Zone.objects.create(city=self.city,name='Zone Other')
        Area.objects.create(city=self.city,zone=other,name='Area Other')
        result=self.client.get('/api/shop/locations/',{'kind':'zone','city':self.city.pk,'q':'Zone'}).json()['results']
        self.assertEqual(len(result),2)
        result=self.client.get('/api/shop/locations/',{'kind':'area','city':self.city.pk,'zone':self.zone.pk,'q':'Area'}).json()['results']
        self.assertEqual(result,[{'id':self.area.pk,'name':'Area A'}])
        transport.assert_not_called()

    @patch.object(Pathao,'transport',side_effect=AssertionError('Browsing must query our database only'))
    def test_browse_lists_are_parent_scoped_searchable_and_paginated(self,transport):
        for index in range(24):Zone.objects.create(city=self.city,name=f'Browse {index:02d}')
        other_city=City.objects.create(name='City B')
        Zone.objects.create(city=other_city,name='Browse elsewhere')
        Zone.objects.create(city=self.city,name='Browse hidden',is_active=False)
        params={'kind':'zone','city':self.city.pk}
        first=self.client.get('/api/shop/locations/',params).json()
        second=self.client.get('/api/shop/locations/',{**params,'page':2}).json()
        self.assertTrue(first['has_more']);self.assertFalse(second['has_more'])
        self.assertEqual(len(first['results'])+len(second['results']),25)
        self.assertFalse(set(row['id'] for row in first['results'])&set(row['id'] for row in second['results']))
        matches=self.client.get('/api/shop/locations/',{**params,'q':'Browse 03'}).json()['results']
        self.assertEqual([row['name'] for row in matches],['Browse 03'])
        areas=self.client.get('/api/shop/locations/',{'kind':'area','city':self.city.pk,'zone':self.zone.pk}).json()['results']
        self.assertEqual(areas,[{'id':self.area.pk,'name':'Area A'}])
        transport.assert_not_called()

    def test_checkout_and_invoice_allow_missing_area(self):
        self.client.force_login(self.user);set_item(self.user,self.product.pk,None,1)
        quote=self.client.get('/api/shop/cart/').json()['quote']
        response=self.client.post('/api/shop/checkout/',{**self.details,'city':self.city.pk,'zone':self.zone.pk,
            'quote':quote,'checkout_key':str(uuid.uuid4())})
        self.assertEqual(response.status_code,200,response.content)
        order=Order.objects.get()
        self.assertEqual(order.zone_record_id,self.zone.pk)
        self.assertIsNone(order.area_record_id);self.assertEqual(order.area,'')
        invoice=self.client.get(f'/api/shop/orders/{order.pk}/invoice/').json()['order']
        self.assertEqual(invoice['area'],'');self.assertEqual(invoice['zone'],self.zone.name)

    def test_manual_invoice_allows_missing_area(self):
        self.client.force_login(self.owner)
        data={'checkout_key':str(uuid.uuid4()),'customer_name':'Manual customer','shipping_fee':'0','delivery_zone':'custom',
              'city':self.city.name,'zone':self.zone.name,'items':json.dumps([{'model':'product','id':self.product.pk,'quantity':1}])}
        preview=self.client.post('/api/control/manual-invoices/preview/',data)
        self.assertEqual(preview.status_code,200,preview.content)
        response=self.client.post('/api/control/manual-invoices/issue/',{**data,'quote':preview.json()['quote']})
        self.assertEqual(response.status_code,200,response.content)
        self.assertIsNone(Order.objects.get().area_record_id)

    def test_empty_area_keeps_city_zone_courier_mapping(self):
        account=self.directory()
        set_item(self.user,self.product.pk,None,1)
        order=place_order(self.user,uuid.uuid4(),{**self.details,**resolve(self.city.pk,'',zone=self.zone.pk)})
        destination=courier_destination(order,account)
        self.assertEqual(destination,{'recipient_city':101,'recipient_zone':102})

    def test_checkout_saves_zone_and_invoice_snapshot(self):
        self.client.force_login(self.user)
        set_item(self.user,self.product.pk,None,1)
        quote=self.client.get('/api/shop/cart/').json()['quote']
        data={**self.details,'city':self.city.pk,'zone':self.zone.pk,'area':self.area.pk,'quote':quote,'checkout_key':str(uuid.uuid4())}
        response=self.client.post('/api/shop/checkout/',data)
        self.assertEqual(response.status_code,200,response.content)
        order=Order.objects.get()
        self.assertEqual(order.zone_record_id,self.zone.pk)
        self.zone.name='Renamed zone';self.zone.save()
        invoice=self.client.get(f'/api/shop/orders/{order.pk}/invoice/').json()['order']
        self.assertEqual(invoice['zone'],'Zone A')
        self.assertEqual(order.zone,'Zone A')
        with self.assertRaises(ValidationError):
            self.area.zone=Zone.objects.create(city=self.city,name='Move target');self.area.save()

    def test_checkout_draft_keeps_valid_zone_without_extending_hold(self):
        self.client.force_login(self.user);set_item(self.user,self.product.pk,None,1)
        cart=self.client.get('/api/shop/cart/').json();expiry=CartItem.objects.get().expires_at
        draft={'city':{'id':self.city.pk},'zone':{'id':self.zone.pk},'area':{'id':self.area.pk}}
        response=self.client.post('/api/shop/cart/draft/',{'expiry':cart['draft_expiry'],'draft':json.dumps(draft)})
        self.assertEqual(response.status_code,200)
        self.assertEqual(Cart.objects.get().checkout_draft['zone']['id'],self.zone.pk)
        self.assertEqual(CartItem.objects.get().expires_at,expiry)
        draft['zone']={'id':999999}
        self.client.post('/api/shop/cart/draft/',{'expiry':cart['draft_expiry'],'draft':json.dumps(draft)})
        self.assertIsNone(Cart.objects.get().checkout_draft['area'])

    def test_manual_invoice_accepts_three_levels_and_preserves_ids(self):
        self.client.force_login(self.owner)
        data={'checkout_key':str(uuid.uuid4()),'customer_name':'Manual customer','shipping_fee':'0','delivery_zone':'custom',
              'city':self.city.name,'zone':self.zone.name,'area':self.area.name,
              'items':json.dumps([{'model':'product','id':self.product.pk,'quantity':1}])}
        preview=self.client.post('/api/control/manual-invoices/preview/',data)
        self.assertEqual(preview.status_code,200,preview.content)
        response=self.client.post('/api/control/manual-invoices/issue/',{**data,'quote':preview.json()['quote']})
        self.assertEqual(response.status_code,200,response.content)
        order=Order.objects.get();self.assertEqual(order.zone_record_id,self.zone.pk)

    def directory(self,environment='sandbox',offset=0):
        from django.utils import timezone
        account=CourierAccount.objects.create(name=environment,environment=environment,store_id=1,cities_refreshed_at=timezone.now())
        city=CourierLocation.objects.create(account=account,kind='cities',external_id=offset+101,name=self.city.name,children_refreshed_at=timezone.now())
        zone=CourierLocation.objects.create(account=account,kind='zones',external_id=offset+102,name=self.zone.name,parent=city,children_refreshed_at=timezone.now())
        CourierLocation.objects.create(account=account,kind='areas',external_id=offset+103,name=self.area.name,parent=zone)
        map_published_directory(account)
        return account

    @patch.object(Pathao,'token',return_value='token')
    @patch.object(Pathao,'book',return_value={'data':{'consignment_id':'ADDRESS-1','delivery_fee':80}})
    def test_booking_reuses_account_specific_mappings(self,book,token):
        account=self.directory();other=self.directory('live',1000)
        order=self.order()
        self.assertEqual(courier_destination(order,other)['recipient_area'],1103)
        transition_order(order.pk,'processing',actor=self.owner);order.refresh_from_db()
        self.client.force_login(self.owner)
        destinations=self.client.get(f'/api/control/operations/orders/{order.pk}/courier/').json()['destinations']
        self.assertEqual(destinations[str(account.pk)]['recipient_zone'],102)
        self.assertEqual(destinations[str(other.pk)]['recipient_zone'],1102)
        self.client.post(f'/api/control/operations/packaging/{order.pk}/pack/',{'item_weight':'.5','item_quantity':1,'checked':'on','expected_version':order.revision})
        response=self.client.post(f'/api/control/operations/orders/{order.pk}/courier/book/',{'account':account.pk,'expected_version':order.revision,'item_weight':'.5','item_quantity':1,'delivery_type':48})
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(book.call_args.args[0]['recipient_zone'],102)
        self.assertEqual(book.call_args.args[0]['recipient_area'],103)

    @patch.object(Pathao,'transport',side_effect=AssertionError('Permissions must be checked before any API import'))
    def test_address_admin_permissions_are_checked_before_directory_import(self,transport):
        account=self.directory()
        self.client.force_login(self.owner)
        with patch.object(admin.site._registry[Zone],'has_add_permission',return_value=False):
            response=self.client.post(f'/api/control/courier-directory/{account.pk}/refresh/')
            self.assertEqual(response.status_code,403)
        transport.assert_not_called()

    def test_new_models_have_both_admin_registrations(self):
        from import_export.admin import ImportExportModelAdmin
        from .models import CourierAddressMapping
        for model in (Zone,CourierAddressMapping):self.assertIsInstance(admin.site._registry[model],ImportExportModelAdmin)

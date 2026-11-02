import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone
from import_export.admin import ImportExportModelAdmin

from .commerce import ShopError, get_cart, place_order, reserved_quantity, set_item, transition_order
from .models import Cart, CartItem, Category, InventoryMovement, Order, OrderItem, Product, ProductVariant, SiteSettings

DETAILS={'customer_name':'Test Customer','email':'test@example.com','phone':'01000000000','address':'Test address','city':'Dhaka','area':'Dhanmondi','postal_code':'','notes':''}


class CommerceTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('buyer')
        self.other=get_user_model().objects.create_user('other')
        self.category=Category.objects.create(name='Rings',slug='rings')
        self.product=Product.objects.create(name='Ring',slug='ring',category=self.category,price=1000,track_stock=True,stock_quantity=2,discount_type='percent',discount_value=10)
        SiteSettings.objects.create(shipping_fee=50,delivery_inside_dhaka=50,delivery_outside_dhaka=100)
        from .models import City,Area
        city=City.objects.create(name='Dhaka');Area.objects.create(city=city,name='Dhanmondi')

    def test_selected_delivery_area_uses_backend_rate_and_rejects_changed_rate(self):
        self.client.force_login(self.user);self.reserve()
        cart=self.client.post('/api/shop/delivery/',{'delivery_zone':'outside'}).json()
        self.assertEqual(cart['shipping_fee'],'100.00')
        site=SiteSettings.load();site.delivery_outside_dhaka=125;site.save()
        response=self.client.post('/api/shop/checkout/',{**DETAILS,'delivery_zone':'outside','checkout_key':uuid.uuid4(),'quote':cart['quote']})
        self.assertEqual(response.status_code,409)
        cart=self.client.get('/api/shop/cart/').json()
        response=self.client.post('/api/shop/checkout/',{**DETAILS,'delivery_zone':'outside','shipping_fee':'1','checkout_key':uuid.uuid4(),'quote':cart['quote']})
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['order']['shipping_fee'],'125.00')

    def test_delivery_advance_claim_is_unpaid_until_staff_verifies_transfer(self):
        from .models import OrderPayment
        site=SiteSettings.load();site.delivery_advance_enabled=True;site.delivery_advance_instructions='Fictional payment instructions';site.delivery_advance_methods=['bkash'];site.save()
        self.client.force_login(self.user);self.reserve()
        cart=self.client.get('/api/shop/cart/').json()
        values={**DETAILS,'checkout_key':str(uuid.uuid4()),'quote':cart['quote'],'payment_method':'delivery_advance','advance_channel':'bkash','advance_reference':'SAMPLE-TRANSFER','delivery_zone':'inside'}
        response=self.client.post('/api/shop/checkout/',values)
        self.assertEqual(response.status_code,200,response.content)
        self.assertTrue(response.json()['order']['advance_pending']);self.assertEqual(response.json()['order']['payment_status'],'unpaid')
        self.assertFalse(OrderPayment.objects.exists())
        order=Order.objects.get();self.assertEqual(order.advance_amount,50)
        staff=get_user_model().objects.create_superuser('verify-payment')
        self.client.force_login(staff)
        response=self.client.post(f'/api/control/operations/orders/{order.pk}/payments/',{'amount':'50','kind':'payment','method':'bkash','reference':'SAMPLE-TRANSFER','occurred_at':timezone.now().isoformat(),'notes':'Checked receipt','operation_key':str(uuid.uuid4()),'expected_version':1})
        self.assertEqual(response.status_code,200,response.content)
        order.refresh_from_db();self.assertTrue(order.advance_verified)
        self.assertEqual(response.json()['amount_due'],'900.00')

    def test_delivery_advance_cannot_bypass_backend_configuration(self):
        self.client.force_login(self.user);self.reserve()
        values={**DETAILS,'checkout_key':str(uuid.uuid4()),'quote':self.client.get('/api/shop/cart/').json()['quote'],'payment_method':'delivery_advance','advance_channel':'bkash','advance_reference':'TEST'}
        self.assertEqual(self.client.post('/api/shop/checkout/',values).status_code,409)
        self.assertFalse(Order.objects.exists())

    def test_dummy_delivery_payment_is_server_calculated_and_idempotent(self):
        from .models import OrderPayment
        site=SiteSettings.load();site.dummy_payments_enabled=True;site.save()
        self.client.force_login(self.user);self.reserve()
        cart=self.client.get('/api/shop/cart/').json();self.assertTrue(cart['advance_enabled'])
        values={**DETAILS,'checkout_key':str(uuid.uuid4()),'quote':cart['quote'],'payment_method':'delivery_advance','amount':'1','payment_status':'paid'}
        response=self.client.post('/api/shop/checkout/',values);self.assertEqual(response.status_code,200,response.content)
        data=response.json()['order'];self.assertEqual(data['received'],'50.00');self.assertEqual(data['amount_due'],'900.00')
        self.assertEqual(data['payment_status'],'partial');self.assertTrue(data['simulated']);self.assertFalse(data['advance_pending'])
        self.assertEqual(self.client.post('/api/shop/checkout/',values).status_code,200)
        self.assertEqual(OrderPayment.objects.count(),1);self.assertTrue(OrderPayment.objects.get().is_simulated)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,1)

    def test_dummy_full_payment_and_backend_disable(self):
        from .models import OrderPayment
        self.client.force_login(self.user);self.reserve()
        cart=self.client.get('/api/shop/cart/').json()
        values={**DETAILS,'checkout_key':str(uuid.uuid4()),'quote':cart['quote'],'payment_method':'pay_now','amount':'1'}
        self.assertEqual(self.client.post('/api/shop/checkout/',values).status_code,409)
        self.assertFalse(OrderPayment.objects.exists());self.assertFalse(Order.objects.exists())
        site=SiteSettings.load();site.dummy_payments_enabled=True;site.save()
        response=self.client.post('/api/shop/checkout/',values);self.assertEqual(response.status_code,200,response.content)
        data=response.json()['order'];self.assertEqual(data['received'],'950.00');self.assertEqual(data['amount_due'],'0.00')
        self.assertEqual(data['payment_status'],'paid');self.assertTrue(data['simulated'])

    def test_checkout_optional_fields_and_area_are_saved(self):
        self.client.force_login(self.user);self.reserve()
        values={k:v for k,v in DETAILS.items() if k not in ['email','postal_code','notes']}
        values.update(checkout_key=str(uuid.uuid4()),quote=self.client.get('/api/shop/cart/').json()['quote'])
        response=self.client.post('/api/shop/checkout/',values)
        self.assertEqual(response.status_code,200,response.content)
        order=Order.objects.get();self.assertEqual(order.email,'');self.assertEqual(order.postal_code,'');self.assertEqual(order.notes,'');self.assertEqual(order.area,'Dhanmondi')
        invoice=self.client.get(f'/api/shop/orders/{order.pk}/invoice/').json()['order']
        self.assertEqual(invoice['area'],'Dhanmondi')

    def test_checkout_rejects_area_from_another_city_and_saves_foreign_keys(self):
        from .models import City,Area
        other_city=City.objects.create(name='Chattogram')
        other_area=Area.objects.create(city=other_city,name='Agrabad')
        self.client.force_login(self.user);self.reserve()
        values={**DETAILS,'checkout_key':str(uuid.uuid4()),'quote':self.client.get('/api/shop/cart/').json()['quote'],'area':str(other_area.pk),'city':str(City.objects.get(name='Dhaka').pk)}
        response=self.client.post('/api/shop/checkout/',values)
        self.assertEqual(response.status_code,400);self.assertFalse(Order.objects.exists())
        values['city']=str(other_city.pk)
        response=self.client.post('/api/shop/checkout/',values)
        self.assertEqual(response.status_code,200,response.content)
        order=Order.objects.get();self.assertEqual(order.city_record,other_city);self.assertEqual(order.area_record,other_area)
        other_city.name='Renamed city';other_city.save()
        order.refresh_from_db();self.assertEqual(order.city,'Chattogram')
        other_area.city=City.objects.get(name='Dhaka')
        with self.assertRaises(ValidationError):other_area.save()

    def test_location_typeahead_search_is_scoped_active_and_limited(self):
        from .models import City,Area
        dhaka=City.objects.get(name='Dhaka');other=City.objects.create(name='Other city')
        Area.objects.create(city=dhaka,name='Mohammadpur')
        Area.objects.create(city=other,name='Mohammadpur Other')
        Area.objects.create(city=dhaka,name='Mohakhali Hidden',is_active=False)
        response=self.client.get('/api/shop/locations/',{'kind':'city','q':'d'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['results'],[{'id':dhaka.pk,'name':'Dhaka'}])
        rows=self.client.get('/api/shop/locations/',{'kind':'area','city':dhaka.pk,'q':'mo'}).json()['results']
        self.assertEqual([row['name'] for row in rows],['Dhanmondi','Mohammadpur'])
        self.assertEqual(self.client.get('/api/shop/locations/',{'kind':'area','q':'m'}).json()['results'],[])
        self.assertEqual(self.client.get('/api/shop/locations/',{'kind':'city','q':''}).json()['results'],[])
        for i in range(25):Area.objects.create(city=dhaka,name=f'Example {i:02d}')
        self.assertEqual(len(self.client.get('/api/shop/locations/',{'kind':'area','city':dhaka.pk,'q':'e'}).json()['results']),20)
        dhaka.is_active=False;dhaka.save()
        self.assertEqual(self.client.get('/api/shop/locations/',{'kind':'area','city':dhaka.pk,'q':'mo'}).json()['results'],[])

    def test_cart_draft_persists_without_extending_hold_and_expires(self):
        import json
        self.client.force_login(self.user);self.reserve()
        cart=self.client.get('/api/shop/cart/').json();expiry=CartItem.objects.get().expires_at
        city=__import__('sanjilas.models',fromlist=['City']).City.objects.get(name='Dhaka')
        area=city.areas.get(name='Dhanmondi')
        values={'customer_name':'Draft customer','phone':'01000000000','city':{'id':city.pk},'area':{'id':area.pk},'payment_method':'pay_now','checkout_open':True}
        response=self.client.post('/api/shop/cart/draft/',{'expiry':cart['draft_expiry'],'draft':json.dumps(values)})
        self.assertEqual(response.status_code,200,response.content)
        saved=self.client.get('/api/shop/cart/').json()['draft']
        self.assertEqual(saved['customer_name'],'Draft customer');self.assertEqual(saved['city']['name'],'Dhaka');self.assertEqual(saved['area']['name'],'Dhanmondi')
        self.assertTrue(saved['checkout_open']);self.assertEqual(CartItem.objects.get().expires_at,expiry)
        self.client.force_login(self.other);self.assertEqual(self.client.get('/api/shop/cart/').json()['draft'],{})
        self.client.force_login(self.user)
        CartItem.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        Cart.objects.filter(user=self.user).update(draft_expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.client.get('/api/shop/cart/').json()['draft'],{})
        self.assertEqual(Cart.objects.get(user=self.user).checkout_draft,{})
        self.assertEqual(self.client.post('/api/shop/cart/draft/',{'expiry':cart['draft_expiry'],'draft':json.dumps(values)}).status_code,409)

    def test_cart_shares_ten_minute_deadline_and_checkout_clears_draft(self):
        import json
        self.client.force_login(self.user);self.reserve()
        first=CartItem.objects.get();self.assertLessEqual(first.expires_at-timezone.now(),timedelta(minutes=10))
        second=Product.objects.create(name='Second ring',slug='second',category=self.category,price=100,track_stock=True,stock_quantity=2)
        set_item(self.user,second.pk,None,1)
        self.assertEqual(CartItem.objects.get(product=second).expires_at,first.expires_at)
        cart=self.client.get('/api/shop/cart/').json()
        self.assertEqual(self.client.post('/api/shop/cart/draft/',{'expiry':cart['draft_expiry'],'draft':json.dumps({'customer_name':'Draft'})}).status_code,200)
        self.checkout()
        self.assertEqual(Cart.objects.get(user=self.user).checkout_draft,{})

    def reserve(self,user=None,quantity=1,variant=None):
        return set_item(user or self.user,self.product.pk,variant.pk if variant else None,quantity)

    def checkout(self,key=None):
        return place_order(self.user,key or uuid.uuid4(),DETAILS)

    def test_reserving_last_unit_blocks_other_customer(self):
        self.reserve(quantity=2)
        with self.assertRaises(ShopError): self.reserve(self.other)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity,2)
        self.assertEqual(reserved_quantity(self.product),2)

    def test_customer_can_update_own_hold_but_not_steal_others(self):
        self.reserve()
        self.reserve(self.other)
        with self.assertRaises(ShopError): self.reserve(quantity=2)
        self.assertEqual(CartItem.objects.get(cart__user=self.user).quantity,1)
        self.reserve(quantity=0)
        self.reserve(self.other,quantity=2)
        self.assertEqual(reserved_quantity(self.product),2)

    def test_expiry_releases_stock_without_a_scheduler(self):
        self.reserve(quantity=2)
        CartItem.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        self.reserve(self.other,quantity=2)
        with self.assertRaises(ShopError): self.checkout()
        self.assertFalse(Order.objects.exists())

    def test_reading_or_updating_cart_does_not_extend_existing_reservation(self):
        self.reserve()
        expiry=CartItem.objects.get().expires_at
        self.client.force_login(self.user)
        self.client.get('/api/shop/cart/')
        self.reserve(quantity=2)
        self.assertEqual(CartItem.objects.get().expires_at,expiry)

    def test_order_snapshots_prices_deducts_once_and_clears_cart(self):
        self.reserve(quantity=2)
        key=uuid.uuid4()
        order=self.checkout(key)
        self.assertEqual(order.subtotal,1800)
        self.assertEqual(order.total,1850)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity,0)
        self.assertFalse(CartItem.objects.exists())
        self.assertEqual(self.checkout(key).pk,order.pk)
        self.assertEqual(InventoryMovement.objects.filter(reason='sale').count(),1)
        self.product.price=2000;self.product.save()
        self.assertEqual(order.items.get().unit_price,900)

    def test_customer_reference_is_short_unique_and_stable(self):
        self.reserve()
        first=self.checkout()
        self.assertRegex(first.reference,r'^ORD-\d{8}-\d{6,}$')
        reference=first.reference
        transition_order(first.pk,'processing')
        first.refresh_from_db()
        self.assertEqual(first.reference,reference)
        self.reserve();second=self.checkout()
        self.assertNotEqual(first.reference,second.reference)
        self.client.force_login(self.user)
        data=self.client.get('/api/shop/orders/').json()['orders']
        self.assertEqual(len({item['reference'] for item in data}),2)
        self.assertEqual(len({item['id'] for item in data}),2)

    def test_invoice_is_private_and_uses_order_snapshot_prices(self):
        self.reserve(quantity=2);order=self.checkout()
        url=f'/api/shop/orders/{order.pk}/invoice/'
        self.assertEqual(self.client.get(url).status_code,401)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code,404)
        self.client.force_login(self.user)
        self.product.refresh_from_db();self.product.price=2000;self.product.save()
        response=self.client.get(url)
        self.assertEqual(response.status_code,200)
        self.assertIn('no-store',response['Cache-Control'])
        data=response.json()['order']
        self.assertEqual(data['invoice_reference'],order.reference.replace('ORD-','INV-',1))
        self.assertEqual(data['items'][0]['unit_price'],'900.00')
        self.assertEqual(data['items'][0]['discount_amount'],'200.00')
        self.assertEqual(data['regular_subtotal'],'2000.00')
        self.assertEqual(data['total'],'1850.00')
        shell=self.client.get(f'/invoice/{order.pk}/')
        self.assertEqual(shell.status_code,200)
        self.assertContains(shell,'noindex, nofollow')

    def test_invoice_terms_are_editable_and_use_current_branding(self):
        self.reserve();order=self.checkout();self.client.force_login(self.user)
        site=SiteSettings.load();site.site_name='Preview Atelier';site.invoice_terms_heading='Delivery information';site.invoice_terms='Inspect before accepting.\nContact {site_name} before the courier leaves.';site.save()
        result=self.client.get(f'/api/shop/orders/{order.pk}/invoice/').json()['site']
        self.assertEqual(result['invoice_terms_heading'],'Delivery information')
        self.assertEqual(result['invoice_generated_note'],'This is a computer-generated invoice and does not require a signature.')
        self.assertEqual(result['invoice_terms'],'Inspect before accepting.\nContact Preview Atelier before the courier leaves.')
        site.invoice_terms='';site.save()
        self.assertEqual(self.client.get(f'/api/shop/orders/{order.pk}/invoice/').json()['site']['invoice_terms'],'')

    def test_staff_invoice_requires_order_and_item_permissions(self):
        from django.contrib.auth.models import Permission
        self.reserve();order=self.checkout()
        staff=get_user_model().objects.create_user('invoice-staff',is_staff=True)
        staff.user_permissions.add(Permission.objects.get(content_type__app_label='sanjilas',codename='view_order'))
        self.client.force_login(staff)
        url=f'/api/shop/orders/{order.pk}/invoice/'
        self.assertEqual(self.client.get(url).status_code,404)
        staff.user_permissions.add(Permission.objects.get(content_type__app_label='sanjilas',codename='view_orderitem'))
        self.assertEqual(self.client.get(url).status_code,200)

    def test_cancellation_returns_stock_exactly_once(self):
        self.reserve()
        order=self.checkout()
        transition_order(order.pk,'cancelled',user=self.user)
        transition_order(order.pk,'cancelled',user=self.user)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity,2)
        self.assertEqual(InventoryMovement.objects.filter(reason='cancellation').count(),1)
        with self.assertRaises(ValidationError): transition_order(order.pk,'processing')

    def test_owner_and_status_boundaries_for_cancellation(self):
        self.reserve();order=self.checkout()
        with self.assertRaises(ShopError): transition_order(order.pk,'cancelled',user=self.other)
        transition_order(order.pk,'processing')
        with self.assertRaises(ShopError): transition_order(order.pk,'cancelled',user=self.user)
        transition_order(order.pk,'shipped')
        with self.assertRaises(ValidationError): transition_order(order.pk,'cancelled')

    def test_variant_reservations_are_separate_and_require_correct_product(self):
        first=ProductVariant.objects.create(product=self.product,name='Small',sku='SMALL',stock_quantity=1)
        second=ProductVariant.objects.create(product=self.product,name='Large',sku='LARGE',stock_quantity=1)
        self.reserve(variant=first)
        with self.assertRaises(ShopError): self.reserve(self.other,variant=first)
        self.reserve(self.other,variant=second)
        with self.assertRaises(ShopError): self.reserve(quantity=1)
        another=Product.objects.create(name='Other',slug='other',category=self.category,price=1000)
        with self.assertRaises(ShopError): set_item(self.user,another.pk,first.pk,1)
        order=self.checkout()
        first.refresh_from_db();second.refresh_from_db()
        self.assertEqual((first.stock_quantity,second.stock_quantity),(0,1))
        self.assertEqual(order.items.get().variant_name,'Small')

    def test_admin_cannot_reduce_stock_below_holds(self):
        self.reserve(quantity=2)
        self.product.stock_quantity=1
        with self.assertRaises(ValidationError): self.product.save()
        self.product.stock_quantity=2;self.product.track_stock=False
        with self.assertRaises(ValidationError): self.product.save()

    def test_stale_admin_form_cannot_overwrite_order_deduction(self):
        stale=Product.objects.get(pk=self.product.pk)
        self.reserve();self.checkout()
        stale.name='Updated'
        with self.assertRaises(ValidationError): stale.save()
        stale.refresh_from_db();stale.name='Updated';stale.save()
        self.assertEqual(stale.stock_quantity,1)

    def test_untracked_backorders_and_unpriced_items_cannot_oversell(self):
        self.product.track_stock=False;self.product.save()
        with self.assertRaises(ShopError): self.reserve()
        self.product.track_stock=True;self.product.stock_quantity=0;self.product.allow_backorder=True;self.product.save()
        with self.assertRaises(ShopError): self.reserve()
        self.product.stock_quantity=2;self.product.price=None;self.product.discount_type='none';self.product.discount_value=0;self.product.save()
        with self.assertRaises(ShopError): self.reserve()

    def test_server_totals_ignore_customer_supplied_prices(self):
        self.client.force_login(self.user)
        self.client.post('/api/shop/cart/items/',{'product_id':self.product.pk,'quantity':1,'price':1})
        response=self.client.post('/api/shop/checkout/',{**DETAILS,'checkout_key':uuid.uuid4(),'quote':self.client.get('/api/shop/cart/').json()['quote'],'total':1,'shipping_fee':0})
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['order']['total'],'950.00')

    def test_csrf_authentication_and_order_isolation(self):
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/api/shop/cart/items/',{}).status_code,403)
        token=client.get('/api/shop/cart/').json()['csrf_token']
        self.assertEqual(client.post('/api/shop/cart/items/',{},HTTP_X_CSRFTOKEN=token).status_code,401)
        self.reserve();order=self.checkout()
        client.force_login(self.other)
        token=client.get('/api/shop/cart/').json()['csrf_token']
        self.assertEqual(client.get('/api/shop/orders/').json()['orders'],[])
        self.assertEqual(client.post(f'/api/shop/orders/{order.pk}/cancel/',{},HTTP_X_CSRFTOKEN=token).status_code,404)
        self.assertEqual(client.post('/api/shop/cart/items/',{'product_id':self.product.pk,'quantity':-1},HTTP_X_CSRFTOKEN=token).status_code,400)

    def test_home_excludes_other_carts_reservations_but_keeps_own_hold(self):
        self.reserve(quantity=2)
        self.client.force_login(self.other)
        product=self.client.get('/api/home/').json()['products'][0]
        self.assertFalse(product['can_purchase'])
        self.assertEqual(product['available_quantity'],0)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/api/home/').json()['products'][0]['available_quantity'],2)

    def test_changed_price_requires_review_before_checkout(self):
        self.client.force_login(self.user)
        self.reserve()
        quote=self.client.get('/api/shop/cart/').json()['quote']
        self.product.price=2000;self.product.save()
        response=self.client.post('/api/shop/checkout/',{**DETAILS,'checkout_key':uuid.uuid4(),'quote':quote})
        self.assertEqual(response.status_code,409)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(CartItem.objects.count(),1)

    def test_invalid_admin_status_transition_is_a_form_error(self):
        self.reserve();order=self.checkout()
        owner=get_user_model().objects.create_superuser('status-owner')
        self.client.force_login(owner)
        response=self.client.post(f'/api/control/models/sanjilas/order/{order.pk}/',{'status':'completed'})
        self.assertEqual(response.status_code,400)
        self.assertIn('status',response.json()['errors'])
        order.refresh_from_db();self.assertEqual(order.status,'placed')

    def test_read_only_commerce_models_cannot_be_imported_or_changed(self):
        owner=get_user_model().objects.create_superuser('owner')
        self.client.force_login(owner)
        for model in [Cart,CartItem,OrderItem,InventoryMovement]:
            self.assertIsInstance(admin.site._registry[model],ImportExportModelAdmin)
            path=f'/api/control/models/sanjilas/{model._meta.model_name}/'
            self.assertEqual(self.client.post(path+'new/',{}).status_code,403)
        self.reserve();order=self.checkout()
        response=self.client.post(f'/api/control/models/sanjilas/order/{order.pk}/',{'status':'cancelled'})
        self.assertEqual(response.status_code,200,response.content)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,2)


class StockConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.users=[get_user_model().objects.create_user(name) for name in ['first','second']]
        category=Category.objects.create(name='Rings',slug='rings')
        self.product=Product.objects.create(name='Last ring',slug='last',category=category,price=1000,track_stock=True,stock_quantity=1)
        for user in self.users: get_cart(user)

    def test_two_simultaneous_customers_cannot_reserve_the_same_last_unit(self):
        barrier=Barrier(2)
        def reserve(user):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    set_item(user,self.product.pk,None,1)
                    return 'reserved'
                except ShopError:
                    return 'blocked'
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(reserve,self.users))
        self.assertCountEqual(results,['reserved','blocked'])
        self.assertEqual(reserved_quantity(self.product),1)

    def test_two_customers_cannot_reserve_the_same_last_variant(self):
        variant=ProductVariant.objects.create(product=self.product,name='Size 7',sku='LAST-7',stock_quantity=1)
        barrier=Barrier(2)
        def reserve(user):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    set_item(user,self.product.pk,variant.pk,1)
                    return 'reserved'
                except ShopError:
                    return 'blocked'
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(reserve,self.users))
        self.assertCountEqual(results,['reserved','blocked'])
        self.assertEqual(reserved_quantity(variant),1)

    def test_simultaneous_checkout_retries_create_only_one_order(self):
        set_item(self.users[0],self.product.pk,None,1)
        barrier=Barrier(2);key=uuid.uuid4()
        def checkout(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return place_order(self.users[0],key,DETAILS).pk
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(checkout,range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(Order.objects.count(),1)
        self.product.refresh_from_db();self.assertEqual(self.product.stock_quantity,0)

from unittest.mock import patch
from types import SimpleNamespace
from django.contrib import admin
from django.test import TestCase, Client, RequestFactory, override_settings
from django.utils import timezone
from .couriers import Pathao, CourierError
from .models import CourierAccount, CourierLocation, Shipment
from .test_couriers import CourierTests, CREDENTIALS


@override_settings(PATHAO={'sandbox':CREDENTIALS,'live':CREDENTIALS}, PATHAO_LIVE_ENABLED=True)
class CourierLocationTests(TestCase):
    def setUp(self):
        CourierTests.setUp(self)
        self.account.cities_refreshed_at=timezone.now();self.account.save()
        self.city=CourierLocation.objects.create(account=self.account,kind='cities',external_id=1,name='Dhaka',children_refreshed_at=timezone.now())
        self.zone=CourierLocation.objects.create(account=self.account,kind='zones',external_id=2,name='Mohammadpur',parent=self.city,children_refreshed_at=timezone.now())
        self.area=CourierLocation.objects.create(account=self.account,kind='areas',external_id=3,name='Test area',parent=self.zone)

    @override_settings(PATHAO={})
    @patch.object(Pathao,'transport',side_effect=AssertionError('Directory reads must never call Pathao'))
    def test_dropdowns_use_database_even_without_credentials(self,transport):
        base=f'/api/control/couriers/{self.account.pk}/'
        for path,expected in [('cities/',1),('zones/?parent=1',2),('areas/?parent=2',3)]:
            for _ in range(2):
                response=self.client.get(base+path)
                self.assertEqual(response.status_code,200,response.content)
                self.assertEqual(response.json()['choices'][0]['id'],expected)
        transport.assert_not_called()

    @patch.object(Pathao,'transport',side_effect=AssertionError('Missing data must not trigger a fetch'))
    def test_missing_directory_never_fetches_automatically(self,transport):
        account=CourierAccount.objects.create(name='Not imported',store_id=10)
        response=self.client.get(f'/api/control/couriers/{account.pk}/cities/')
        self.assertEqual(response.status_code,400)
        self.assertIn('not been imported',response.content.decode())
        transport.assert_not_called()

    @patch.object(Pathao,'token',return_value='token')
    @patch.object(Pathao,'cities',side_effect=AssertionError('Booking must not fetch cities'))
    @patch.object(Pathao,'zones',side_effect=AssertionError('Booking must not fetch zones'))
    @patch.object(Pathao,'areas',side_effect=AssertionError('Booking must not fetch areas'))
    @patch.object(Pathao,'book',return_value={'data':{'consignment_id':'SAVED-1','delivery_fee':80}})
    def test_booking_validates_saved_ids_only(self,book,areas,zones,cities,token):
        response=self.client.post(self.base+'book/',{**self.form,'recipient_city':1,'recipient_zone':2,'recipient_area':3})
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(book.call_args.args[0]['recipient_area'],3)
        cities.assert_not_called();zones.assert_not_called();areas.assert_not_called()

    @patch.object(Pathao,'transport',side_effect=AssertionError('Invalid IDs must not call Pathao'))
    def test_wrong_parent_and_unavailable_area_are_rejected_locally(self,transport):
        self.area.available=False;self.area.save()
        for values in [dict(recipient_city=99),dict(recipient_city=1,recipient_zone=99),dict(recipient_city=1,recipient_zone=2,recipient_area=3)]:
            self.assertEqual(self.client.post(self.base+'book/',{**self.form,**values}).status_code,400)
        self.assertFalse(Shipment.objects.exists())
        transport.assert_not_called()

    def run_import(self):
        from .courier_directory_sync import process_one
        for _ in range(30):
            if not process_one(): return
        self.fail('Import did not finish')

    @patch.object(Pathao,'cities',return_value={'data':{'data':[{'city_id':1,'city_name':'Dhaka'},{'city_id':4,'city_name':'New City'}]}})
    @patch.object(Pathao,'zones',side_effect=lambda city:{'data':{'data':[{'zone_id':city*10,'zone_name':f'Zone {city}'}]}})
    @patch.object(Pathao,'areas',side_effect=lambda zone:{'data':{'data':[{'area_id':zone*10,'area_name':f'Area {zone}'}]}})
    def test_one_click_imports_all_cities_zones_and_areas(self,areas,zones,cities):
        from .models import CourierDirectorySync
        url=f'/api/control/courier-directory/{self.account.pk}/refresh/'
        self.assertEqual(self.client.get(url).status_code,405)
        response=self.client.post(url)
        self.assertEqual(response.status_code,202,response.content)
        cities.assert_not_called()
        self.run_import()
        job=CourierDirectorySync.objects.get(account=self.account)
        self.assertEqual(job.state,'completed')
        self.assertEqual((job.cities,job.zones,job.areas),(2,2,2))
        cities.assert_called_once()
        self.assertEqual([call.args[0] for call in zones.call_args_list],[1,4])
        self.assertEqual([call.args[0] for call in areas.call_args_list],[10,40])
        node=CourierLocation.objects.get(account=self.account,kind='areas',external_id=400)
        self.assertEqual(node.parent.external_id,40)
        self.assertEqual(node.parent.parent.external_id,4)
        self.assertEqual(self.client.get(f'/api/control/couriers/{self.account.pk}/areas/?parent=40').json()['choices'][0]['id'],400)

    @patch.object(Pathao,'cities',side_effect=CourierError('Offline'))
    def test_failed_full_import_keeps_last_good_data(self,cities):
        from .models import CourierDirectorySync
        response=self.client.post(f'/api/control/courier-directory/{self.account.pk}/refresh/')
        self.assertEqual(response.status_code,202)
        self.run_import()
        self.assertEqual(CourierDirectorySync.objects.get().state,'failed')
        self.city.refresh_from_db();self.assertTrue(self.city.is_active)
        self.assertEqual(self.city.name,'Dhaka')

    @patch('sanjilas.courier_directory_sync.time.sleep')
    @patch.object(Pathao,'cities',side_effect=[CourierError('Timeout',retryable=True),CourierError('Timeout',retryable=True),{'data':{'data':[{'city_id':4,'city_name':'New City'}]}}])
    @patch.object(Pathao,'zones',return_value={'data':{'data':[]}})
    def test_transient_location_reads_retry_with_bound(self,zones,cities,sleep):
        from .models import CourierDirectorySync
        self.client.post(f'/api/control/courier-directory/{self.account.pk}/refresh/')
        self.run_import()
        self.assertEqual(CourierDirectorySync.objects.get().state,'completed')
        self.assertEqual(cities.call_count,3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list],[1,2])

    @patch('sanjilas.courier_directory_sync.time.sleep')
    @patch.object(Pathao,'cities',side_effect=CourierError('Timeout',retryable=True))
    def test_exhausted_reads_report_reason_and_preserve_data(self,cities,sleep):
        from .models import CourierDirectorySync
        self.client.post(f'/api/control/courier-directory/{self.account.pk}/refresh/')
        self.run_import()
        job=CourierDirectorySync.objects.get()
        self.assertEqual(job.state,'failed')
        self.assertIn('connection failed or timed out',job.last_error)
        self.assertEqual(cities.call_count,3)
        self.city.refresh_from_db();self.assertTrue(self.city.is_active)

    @patch.object(Pathao,'cities',return_value={'data':{'data':[{'city_id':4,'city_name':'New City'}]}})
    @patch.object(Pathao,'zones',side_effect=[CourierError('Offline'),{'data':{'data':[]}}])
    def test_retry_resumes_and_duplicate_click_does_not_duplicate_import(self,zones,cities):
        from .models import CourierDirectorySync
        from .courier_directory_sync import process_one
        url=f'/api/control/courier-directory/{self.account.pk}/refresh/'
        first=self.client.post(url).json()['sync']['id']
        self.assertEqual(self.client.post(url).json()['sync']['id'],first)
        self.assertEqual(CourierDirectorySync.objects.count(),1)
        process_one()  # cities staged but not published
        self.assertFalse(CourierLocation.objects.filter(account=self.account,external_id=4).exists())
        process_one()  # zones failed
        self.assertEqual(CourierDirectorySync.objects.get().state,'failed')
        self.assertEqual(self.client.post(url).json()['sync']['id'],first)
        self.run_import()
        self.assertEqual(CourierDirectorySync.objects.get().state,'completed')
        cities.assert_called_once()
        self.assertEqual(zones.call_count,2)

    @patch.object(Pathao,'cities')
    def test_refresh_respects_permissions_hooks_and_csrf(self,cities):
        url=f'/api/control/courier-directory/{self.account.pk}/refresh/'
        with patch.object(admin.site._registry[CourierLocation],'has_change_permission',return_value=False):
            self.assertEqual(self.client.post(url,{'kind':'cities'}).status_code,403)
        client=Client(enforce_csrf_checks=True);client.force_login(self.owner)
        self.assertEqual(client.post(url,{'kind':'cities'}).status_code,403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(url,{'kind':'cities'}).status_code,403)
        cities.assert_not_called()

    def test_directory_advertises_refresh_permission_without_allowing_generic_edits(self):
        response=self.client.get('/api/control/courier-directory/')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()['accounts'][0]['can_refresh'])
        response=self.client.post(f'/api/control/models/sanjilas/courierlocation/{self.city.pk}/',{'name':'Changed'})
        self.assertEqual(response.status_code,403)
        with patch.object(admin.site._registry[CourierLocation],'has_change_permission',return_value=False):
            self.assertFalse(self.client.get('/api/control/courier-directory/').json()['accounts'][0]['can_refresh'])

    @patch('sanjilas.courier_directory_sync.start_worker')
    def test_one_request_launches_worker_after_job_commit(self,worker):
        with self.captureOnCommitCallbacks(execute=True):
            response=self.client.post(f'/api/control/courier-directory/{self.account.pk}/refresh/')
            self.assertEqual(response.status_code,202)
            worker.assert_not_called()
        worker.assert_called_once()

    def test_full_import_respects_location_object_scope(self):
        with patch.object(admin.site._registry[CourierLocation],'get_queryset',return_value=CourierLocation.objects.none()):
            response=self.client.post(f'/api/control/courier-directory/{self.account.pk}/refresh/')
            self.assertEqual(response.status_code,403)

    def test_django_admin_has_one_complete_refresh_action(self):
        from .models import CourierDirectorySync
        request=RequestFactory().post('/admin/sanjilas/courieraccount/')
        request.user=self.owner;request.resolver_match=SimpleNamespace(url_name='sanjilas_courieraccount_changelist')
        ma=admin.site._registry[CourierAccount]
        with patch.object(ma,'message_user'):
            ma.update_all_locations(request,CourierAccount.objects.filter(pk=self.account.pk))
        self.assertEqual(CourierDirectorySync.objects.get().account_id,self.account.pk)

    @patch.object(Pathao,'transport',side_effect=AssertionError('No cross-environment fallback'))
    def test_directory_scope_and_environment_are_isolated(self,transport):
        live=CourierAccount.objects.create(name='Live',environment='live',store_id=99)
        self.assertEqual(self.client.get(f'/api/control/couriers/{live.pk}/cities/').status_code,400)
        with patch.object(admin.site._registry[CourierAccount],'get_queryset',return_value=CourierAccount.objects.none()):
            self.assertEqual(self.client.get(f'/api/control/couriers/{self.account.pk}/cities/').status_code,404)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(f'/api/control/couriers/{self.account.pk}/cities/').status_code,403)
        transport.assert_not_called()

import io
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from PIL import Image
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from .ai_service import AIError, generate, reserve, object_schema, STRING
from .models import AIProductDraft, AIUsageCounter, Category, Product, ProductImage, SiteSettings


def photo(colour='red'):
    stream = io.BytesIO()
    Image.new('RGB', (40, 40), colour).save(stream, 'PNG')
    return SimpleUploadedFile('photo.png', stream.getvalue(), 'image/png')


def provider(output, tokens=200):
    from unittest.mock import MagicMock
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps({
        'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(output)}]}}],
        'usageMetadata': {'totalTokenCount': tokens},
    }).encode()
    return response


@override_settings(GEMINI_API_KEY='test-key-never-real', GEMINI_MODEL='gemini-3.5-flash-lite')
class AssistantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_superuser('ai-owner', 'ai@example.com', 'test-password')
        cls.customer = get_user_model().objects.create_user('ai-customer')
        cls.staff = get_user_model().objects.create_user('ai-editor', is_staff=True)
        cls.category = Category.objects.create(name='Earrings', slug='earrings')
        cls.product = Product.objects.create(name='Floral earrings', category=cls.category, price='650', stock_quantity=3)
        cls.site = SiteSettings.objects.create(ai_chat_enabled=True)

    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media.cleanup)

    def suggestions(self, **changes):
        return {'name': 'Floral earrings', 'subtitle': 'A floral accent', 'description': 'A red floral design.',
                'color': 'Red', 'image_alt': 'Red floral earrings', 'category': self.category.pk,
                'tags': [], 'collections': [], 'image_order': [0], 'single_product': True,
                'unknowns': ['Confirm material.'], **changes}

    def draft(self, **post):
        self.client.force_login(self.owner)
        return self.client.post('/api/control/assistant/draft/', {'images': photo(), 'price': '650', **post})

    def save(self, draft_id, **post):
        return self.client.post(f'/api/control/assistant/drafts/{draft_id}/save/', {
            'images': photo(), 'name': 'Reviewed earrings', 'description': 'Confirmed red floral design.',
            'category': self.category.pk, 'price': '650', 'image_order': '[0]', **post})

    @patch('sanjilas.ai_service.urlopen')
    def test_draft_approval_defaults_stock_and_is_idempotent(self, transport):
        transport.return_value = provider(self.suggestions())
        count = Product.objects.count()
        result = self.draft()
        self.assertEqual(result.status_code, 200, result.content)
        data = result.json()
        self.assertEqual(data['draft']['stock_quantity'], 1)
        self.assertEqual(Product.objects.count(), count)
        saved = self.save(data['id'], is_active='on')
        self.assertEqual(saved.status_code, 200, saved.content)
        product = Product.objects.get(pk=saved.json()['id'])
        self.assertEqual(product.stock_quantity, 1)
        self.assertTrue(product.is_active)
        self.assertTrue(product.image.name.endswith('.webp'))
        self.assertTrue(LogEntry.objects.filter(object_id=str(product.pk)).exists())
        again = self.save(data['id'])
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(Product.objects.count(), count + 1)
        self.assertEqual(transport.call_count, 1)
        sent = json.loads(transport.call_args.args[0].data)
        self.assertEqual(sent['generationConfig']['thinkingConfig'], {'thinkingLevel': 'MINIMAL'})
        self.assertNotIn('test-key', transport.call_args.args[0].full_url)

    @patch('sanjilas.ai_service.urlopen')
    def test_zero_stock_remains_zero_and_unpublished_default(self, transport):
        transport.return_value = provider(self.suggestions())
        draft = self.draft(stock_quantity='0').json()
        self.assertEqual(draft['draft']['stock_quantity'], 0)
        response = self.save(draft['id'], stock_quantity='0')
        self.assertEqual(response.status_code, 200, response.content)
        product = Product.objects.get(pk=response.json()['id'])
        self.assertEqual(product.stock_quantity, 0)
        self.assertFalse(product.is_active)

    @patch('sanjilas.ai_service.urlopen')
    def test_gallery_is_saved_in_selected_order(self, transport):
        transport.return_value = provider(self.suggestions(image_order=[1, 0]))
        self.client.force_login(self.owner)
        draft = self.client.post('/api/control/assistant/draft/', {'images': [photo(), photo('blue')], 'price': '100'}).json()
        response = self.client.post(f"/api/control/assistant/drafts/{draft['id']}/save/", {
            'images': [photo(), photo('blue')], 'price': '100', 'name': 'Gallery earrings',
            'category': self.category.pk, 'image_order': '[1,0]',
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(ProductImage.objects.filter(product_id=response.json()['id']).count(), 1)

    @patch('sanjilas.ai_service.urlopen')
    def test_rejects_expired_drafts_changed_images_and_other_owners(self, transport):
        transport.return_value = provider(self.suggestions())
        draft = self.draft().json()
        response = self.save(draft['id'], images=photo('blue'))
        self.assertEqual(response.status_code, 400)
        AIProductDraft.objects.filter(pk=draft['id']).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.save(draft['id']).status_code, 409)
        self.client.force_login(self.staff)
        self.assertEqual(self.save(draft['id']).status_code, 403)

    @patch('sanjilas.ai_service.urlopen')
    def test_permissions_and_csrf_precede_provider_call(self, transport):
        for user in [self.customer, self.staff]:
            self.client.force_login(user)
            self.assertEqual(self.client.post('/api/control/assistant/draft/', {'price': '10', 'images': photo()}).status_code, 403)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post('/api/control/assistant/draft/', {'price': '10', 'images': photo()}).status_code, 403)
        self.assertEqual(client.post('/api/shop/assistant/chat/', {'message': 'Wedding'}).status_code, 403)
        transport.assert_not_called()

    @patch('sanjilas.ai_service.urlopen')
    def test_ambiguous_photos_and_invented_category_fail_closed(self, transport):
        transport.return_value = provider(self.suggestions(single_product=False))
        self.assertEqual(self.draft().status_code, 400)
        transport.return_value = provider(self.suggestions(category=999999))
        self.assertEqual(self.draft().status_code, 503)
        self.assertEqual(AIProductDraft.objects.count(), 0)

    @patch('sanjilas.ai_service.urlopen')
    def test_admin_queryset_and_readonly_fields_are_respected(self, transport):
        self.client.force_login(self.owner)
        ma = admin.site._registry[Product]
        transport.return_value = provider(self.suggestions())
        with patch.object(ma, 'has_add_permission', return_value=False):
            self.assertEqual(self.client.post('/api/control/assistant/draft/').status_code, 403)
        transport.assert_not_called()

    @patch('sanjilas.ai_service.urlopen')
    def test_chat_returns_only_available_catalog_and_current_prices(self, transport):
        transport.return_value = provider({'reply': 'These suit a floral dress.', 'product_ids': [self.product.pk]})
        response = self.client.post('/api/shop/assistant/chat/', {'message': 'Earrings for a wedding'})
        self.assertEqual(response.status_code, 200, response.content)
        card = response.json()['products'][0]
        self.assertEqual(card['price'], '650.00')
        self.assertEqual(card['url'], f'/shop/products/{self.product.slug}/')
        self.assertEqual(set(card), {'id', 'name', 'price', 'currency', 'url', 'image', 'image_alt'})
        counter = AIUsageCounter.objects.get(key=f'store:{timezone.localdate().isoformat()}')
        self.assertEqual(counter.calls, 1)
        self.assertEqual(counter.reserved_tokens, 200)
        self.assertEqual(counter.actual_tokens, 200)

    @patch('sanjilas.ai_service.urlopen')
    def test_chat_rechecks_stock_after_model_response(self, transport):
        def reply(*args, **kwargs):
            Product.objects.filter(pk=self.product.pk).update(stock_quantity=0)
            return provider({'reply': 'Here is a suggestion.', 'product_ids': [self.product.pk]})
        transport.side_effect = reply
        response = self.client.post('/api/shop/assistant/chat/', {'message': 'Wedding earrings'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['products'], [])

    @patch('sanjilas.ai_service.urlopen')
    def test_photo_consent_size_and_text_limits(self, transport):
        for data in [{'message': 'Dress', 'image': photo()}, {'message': 'x' * 2001},
                     {'message': 'Dress', 'image': SimpleUploadedFile('bad.jpg', b'invalid'), 'photo_consent': 'yes'}]:
            self.assertEqual(self.client.post('/api/shop/assistant/chat/', data).status_code, 400)
        transport.assert_not_called()

    @patch('sanjilas.ai_service.urlopen')
    def test_daily_limit_and_provider_failure_do_not_retry(self, transport):
        SiteSettings.objects.filter(pk=1).update(ai_guest_daily_limit=1)
        self.client.get('/api/shop/assistant/')
        from urllib.error import URLError
        transport.side_effect = URLError('provider failure with secret details')
        response = self.client.post('/api/shop/assistant/chat/', {'message': 'Wedding'})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('secret', response.content.decode())
        response = self.client.post('/api/shop/assistant/chat/', {'message': 'Wedding'})
        self.assertEqual(response.status_code, 429, response.content)
        self.assertEqual(transport.call_count, 1)

    @patch('sanjilas.ai_service.urlopen')
    def test_global_budget_ip_limit_image_limit_and_inflight_gate(self, transport):
        transport.return_value = provider({'reply': 'Which occasion?', 'product_ids': []})
        SiteSettings.objects.filter(pk=1).update(ai_daily_token_budget=1)
        response = self.client.post('/api/shop/assistant/chat/', {'message': 'Wedding'})
        self.assertEqual(response.status_code, 429, response.content)
        SiteSettings.objects.filter(pk=1).update(ai_daily_token_budget=200000, ai_ip_daily_limit=1)
        self.assertEqual(self.client.post('/api/shop/assistant/chat/', {'message': 'Wedding'}).status_code, 200)
        other = Client()
        self.assertEqual(other.post('/api/shop/assistant/chat/', {'message': 'Wedding'}).status_code, 429)
        SiteSettings.objects.filter(pk=1).update(ai_ip_daily_limit=40, ai_image_daily_limit=0)
        self.assertEqual(self.client.post('/api/shop/assistant/chat/', {'message': 'Dress', 'image': photo(), 'photo_consent': 'yes'}).status_code, 429)
        AIUsageCounter.objects.filter(key__startswith='lease:').update(busy_until=timezone.now() + timedelta(minutes=1))
        response = self.client.post('/api/shop/assistant/chat/', {'message': 'Wedding'})
        self.assertEqual(response.status_code, 429, response.content)
        self.assertEqual(transport.call_count, 1)

    @override_settings(GEMINI_API_KEY='')
    @patch('sanjilas.ai_service.urlopen')
    def test_missing_key_and_disabled_chat(self, transport):
        self.assertFalse(self.client.get('/api/shop/assistant/').json()['enabled'])
        self.assertEqual(self.client.post('/api/shop/assistant/chat/', {'message': 'Wedding'}).status_code, 503)
        transport.assert_not_called()

    def test_new_models_have_registry_driven_readonly_controls(self):
        self.client.force_login(self.owner)
        models = {item['key']: item for item in self.client.get('/api/control/session/').json()['models']}
        for key in ('sanjilas.aiusagecounter', 'sanjilas.aiproductdraft'):
            self.assertTrue(models[key]['permissions']['view'])
            self.assertFalse(models[key]['permissions']['add'])
            self.assertFalse(models[key]['permissions']['change'])
            self.assertFalse(models[key]['permissions']['delete'])

    @patch('sanjilas.ai_service.urlopen')
    def test_failed_admin_hook_rolls_back_product_and_uploaded_files(self, transport):
        from pathlib import Path
        transport.return_value = provider(self.suggestions())
        draft = self.draft().json()
        count = Product.objects.count()
        with patch.object(admin.site._registry[Product], 'save_related', side_effect=ValidationError('Hook rejected product')):
            self.assertEqual(self.save(draft['id']).status_code, 400)
        self.assertEqual(Product.objects.count(), count)
        self.assertFalse(any(p.is_file() for p in Path(self.media.name).rglob('*')))


class ConcurrentQuotaTests(TransactionTestCase):
    def test_parallel_requests_cannot_exceed_store_quota(self):
        site = SiteSettings.objects.create(ai_store_daily_limit=1)
        users = [get_user_model().objects.create_user(f'parallel-{i}') for i in range(2)]

        def attempt(user):
            close_old_connections()
            request = RequestFactory().post('/')
            request.user = user
            try:
                reserve(request, site, 100, 0)
                return 'allowed'
            except AIError:
                return 'limited'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, users))
        self.assertCountEqual(results, ['allowed', 'limited'])

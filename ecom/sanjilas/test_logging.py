import json
import logging
import sys
from unittest import TestCase
from unittest.mock import patch
from django.http import HttpResponse
from django.test import RequestFactory
from .logging_config import JsonFormatter, RequestLoggingMiddleware, request_id


class OperationalLoggingTests(TestCase):
    def test_exception_values_are_not_serialized(self):
        try:
            raise ValueError('password=secret customer@example.com')
        except ValueError:
            record = logging.LogRecord('django.request', logging.ERROR, __file__, 1,
                                       'token=secret', (), sys.exc_info())
        result = JsonFormatter().format(record)
        self.assertNotIn('secret', result)
        self.assertNotIn('customer@example.com', result)
        self.assertEqual(json.loads(result)['exception_type'], 'ValueError')
        self.assertTrue(json.loads(result)['traceback'])

    def test_request_correlation_without_payload(self):
        request = RequestFactory().post('/secret/?password=secret', {'password': 'secret'})
        middleware = RequestLoggingMiddleware(lambda request: HttpResponse(status=403))
        with patch.object(middleware.logger, 'log') as emit:
            response = middleware(request)
        self.assertEqual(len(response['X-Request-ID']), 32)
        fields = emit.call_args.kwargs['extra']
        self.assertEqual(fields['status'], 403)
        self.assertEqual(fields['route'], '[unresolved]')
        self.assertGreaterEqual(fields['duration_ms'], 0)
        self.assertNotIn('secret', str(fields))
        self.assertEqual(request_id.get(), '-')

    def test_context_reset_on_exception(self):
        def fail(request):
            raise RuntimeError('private')
        middleware = RequestLoggingMiddleware(fail)
        with patch.object(middleware.logger, 'log') as emit:
            with self.assertRaises(RuntimeError):
                middleware(RequestFactory().get('/'))
        self.assertEqual(emit.call_args.kwargs['extra']['status'], 500)
        self.assertEqual(request_id.get(), '-')

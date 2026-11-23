"""Structured operational logs without request payloads or exception values."""
import contextvars
import json
import logging
import traceback
import uuid
from datetime import datetime, timezone
from time import perf_counter


request_id = contextvars.ContextVar('log_request_id', default='-')


class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            'time': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'request_id': request_id.get(),
            'process': record.process,
        }
        # Only application-authored structured fields are included. Third-party
        # messages can contain credentials, URLs, SQL parameters or customer data.
        entry['event'] = getattr(record, 'event', 'log_record')
        for key in ('method', 'route', 'status', 'duration_ms'):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info and record.exc_info[0]:
            entry['exception_type'] = record.exc_info[0].__name__
            entry['traceback'] = [
                {'file': frame.filename, 'line': frame.lineno, 'function': frame.name}
                for frame in traceback.extract_tb(record.exc_info[2])
            ]
        entry['source'] = f'{record.pathname}:{record.lineno}'
        return json.dumps(entry, ensure_ascii=True)


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger('sanjilas.requests')

    def __call__(self, request):
        identifier = uuid.uuid4().hex
        token = request_id.set(identifier)
        started = perf_counter()
        status = 500
        try:
            response = self.get_response(request)
            status = response.status_code
            response['X-Request-ID'] = identifier
            return response
        finally:
            match = getattr(request, 'resolver_match', None)
            self.logger.log(
                logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO,
                'request_completed',
                extra={
                    'event': 'request_completed',
                    'method': request.method,
                    # Route patterns avoid recording tokens and identifiers in URLs.
                    'route': str(getattr(match, 'route', '') or '[unresolved]'),
                    'status': status,
                    'duration_ms': round((perf_counter() - started) * 1000, 2),
                },
            )
            request_id.reset(token)

"""Bounded, server-only Gemini transport and PostgreSQL-backed usage gates."""
import base64
import hashlib
import io
import json
import re
import warnings
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import AIUsageCounter
from .tracking import client_ip


class AIError(Exception):
    def __init__(self, key='ai_failed', status=503):
        self.key, self.status = key, status


def image_parts(files, maximum):
    if not files or len(files) > maximum:
        raise AIError('ai_invalid', 400)
    parts, hashes = [], []
    for upload in files:
        if upload.size > 5 * 1024 * 1024:
            raise AIError('ai_invalid', 400)
        raw = upload.read()
        upload.seek(0)
        hashes.append(hashlib.sha256(raw).hexdigest())
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as source:
                    if source.width * source.height > 16_000_000:
                        raise ValueError
                    source.load()
                    image = ImageOps.exif_transpose(source).convert('RGB')
                    image.thumbnail((1024, 1024))
                    output = io.BytesIO()
                    image.save(output, 'JPEG', quality=80)
            parts.append({'inlineData': {'mimeType': 'image/jpeg', 'data': base64.b64encode(output.getvalue()).decode()}})
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise AIError('ai_invalid', 400) from None
    return parts, hashes


def identity(request):
    if request.user.is_authenticated:
        return f'user:{request.user.pk}'
    if not request.session.session_key:
        request.session.create()
    return 'guest:' + hashlib.sha256(request.session.session_key.encode()).hexdigest()[:32]


def reserve(request, site, tokens, images, operator=False):
    # Session creation must survive a quota rejection transaction rollback.
    who = identity(request)
    return _reserve(request, site, tokens, images, operator, who)


@transaction.atomic
def _reserve(request, site, tokens, images, operator, who):
    # This persistent row serializes all quota updates across Django workers.
    lock, _ = AIUsageCounter.objects.get_or_create(key='lock')
    AIUsageCounter.objects.select_for_update().get(pk=lock.pk)
    now = timezone.now()
    day, minute = timezone.localdate().isoformat(), now.strftime('%Y%m%d%H%M')
    scope = 'admin' if operator else 'chat'
    ip_hash = hashlib.sha256(str(client_ip(request)).encode()).hexdigest()[:32]
    limits = [
        (f'store:{day}', site.ai_store_daily_limit, 1),
        (f'{scope}:{who}:{day}', site.ai_admin_daily_limit if operator else site.ai_customer_daily_limit if request.user.is_authenticated else site.ai_guest_daily_limit, 1),
        (f'{scope}:{who}:{minute}', site.ai_burst_limit, 1),
    ]
    if not operator:
        limits.append((f'ip:{ip_hash}:{day}', site.ai_ip_daily_limit, 1))
        if images:
            limits.append((f'images:{who}:{day}', site.ai_image_daily_limit, images))
    rows = []
    for key, limit, amount in limits:
        row, _ = AIUsageCounter.objects.get_or_create(key=key)
        if row.calls + amount > limit:
            raise AIError('ai_limit', 429)
        rows.append((row, amount))
    store = rows[0][0]
    if store.reserved_tokens + tokens > site.ai_daily_token_budget:
        raise AIError('ai_limit', 429)
    lease, _ = AIUsageCounter.objects.get_or_create(key=f'lease:{scope}:{who}')
    if lease.busy_until and lease.busy_until > now:
        raise AIError('ai_limit', 429)
    lease.busy_until = now + timedelta(seconds=45)
    lease.save(update_fields=['busy_until', 'updated_at'])
    for row, amount in rows:
        row.calls += amount
        if row.pk == store.pk:
            row.reserved_tokens += tokens
        row.save(update_fields=['calls', 'reserved_tokens', 'updated_at'])
    return store.pk, lease.pk, lease.busy_until


def generate(request, site, instruction, context, schema, images=(), operator=False):
    model = site.ai_model or settings.GEMINI_MODEL
    if not settings.GEMINI_API_KEY or not re.fullmatch(r'[a-zA-Z0-9._-]{1,100}', model):
        raise AIError('ai_unavailable')
    text = json.dumps(context, ensure_ascii=True)
    if len(text.encode()) > 48000:
        raise AIError('ai_invalid', 400)
    max_output = 2048 if operator else 512
    # Bytes deliberately overestimate text tokens; resized images get ample allowance.
    allowance = len((instruction + text + json.dumps(schema)).encode()) + 8192 * len(images) + max_output
    store_pk, lease_pk, lease_until = reserve(request, site, allowance, len(images), operator)
    payload = {
        'systemInstruction': {'parts': [{'text': instruction}]},
        'contents': [{'role': 'user', 'parts': [{'text': text}, *images]}],
        'generationConfig': {'responseMimeType': 'application/json', 'responseJsonSchema': schema,
                             'maxOutputTokens': max_output,
                             'thinkingConfig': {'thinkingBudget': 0} if model.startswith('gemini-2.5') else {'thinkingLevel': 'MINIMAL'}},
    }
    try:
        req = Request(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                      data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'x-goog-api-key': settings.GEMINI_API_KEY}, method='POST')
        with urlopen(req, timeout=30) as response:
            raw = response.read(256001)
            if len(raw) > 256000:
                raise AIError()
            result = json.loads(raw)
        usage = result.get('usageMetadata', {}).get('totalTokenCount')
        if type(usage) is int and 0 <= usage < 10_000_000:
            AIUsageCounter.objects.filter(pk=store_pk).update(actual_tokens=F('actual_tokens') + usage,
                reserved_tokens=F('reserved_tokens') + usage - allowance)
        candidate = result['candidates'][0]
        if candidate.get('finishReason') != 'STOP':
            raise AIError()
        output = json.loads(''.join(part.get('text', '') for part in candidate['content']['parts'] if not part.get('thought')))
        if not isinstance(output, dict):
            raise AIError()
        return output
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError):
        # Never return provider bodies, which can include prompts or credentials.
        raise AIError() from None
    finally:
        AIUsageCounter.objects.filter(pk=lease_pk, busy_until=lease_until).update(busy_until=None)


def object_schema(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


STRING = {'type': 'string'}
INTEGERS = {'type': 'array', 'items': {'type': 'integer'}, 'maxItems': 6}

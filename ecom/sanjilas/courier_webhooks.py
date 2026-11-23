"""Persist callbacks quickly; verify delivery state via authenticated courier reads."""
import hashlib
import hmac
import json
from datetime import timedelta
from django.conf import settings
from django.contrib import admin
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .couriers import adapter, CourierError
from .models import CourierEvent, Order, PackagingTask, Shipment


@csrf_exempt  # External callbacks use the configured URL token and signature, not staff sessions.
@require_POST
def pathao(request, environment, token):
    config = settings.PATHAO_WEBHOOK.get(environment, {})
    if (not all(config.get(k) for k in ('url_token', 'signature_secret', 'integration_secret'))
            or not hmac.compare_digest(token, config.get('url_token', ''))
            or not hmac.compare_digest(request.headers.get('X-PATHAO-Signature', ''), config.get('signature_secret', ''))):
        return JsonResponse({'error':'Invalid courier callback credentials.'}, status=403)
    def accepted():
        response = JsonResponse({'status':202, 'message':'Accepted', 'data':None}, status=202)
        response['X-Pathao-Merchant-Webhook-Integration-Secret'] = config['integration_secret']
        return response
    if len(request.body) > 32768:
        return JsonResponse({'error':'Callback too large.'}, status=413)
    try:
        body = json.loads(request.body)
        if not isinstance(body, dict): raise ValueError
        event = body.get('event', '')
        if not isinstance(event, str) or len(event) > 100: raise ValueError
        if event == 'webhook_integration': return accepted()
        consignment = body.get('consignment_id', '')
        merchant = body.get('merchant_order_id', '')
        if not all(isinstance(v, str) and 0 < len(v) <= 100 for v in (consignment, merchant, event)):
            raise ValueError
    except (ValueError, TypeError, UnicodeDecodeError):
        return JsonResponse({'error':'Invalid courier callback.'}, status=400)
    row = Shipment.objects.filter(environment=environment, account__provider='pathao', merchant_order_id=merchant).first()
    if not row or (row.consignment_id and row.consignment_id != consignment):
        return JsonResponse({'error':'Unknown courier shipment.'}, status=404)
    # Store only references; callbacks never directly set delivery, fee, stock or payments.
    fingerprint = hashlib.sha256(environment.encode()+json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    CourierEvent.objects.get_or_create(fingerprint=fingerprint, defaults={'shipment':row, 'event':event, 'consignment_id':consignment})
    return accepted()


def apply_verified_status(row, result):
    """Called only with an authenticated provider response while holding the order lock."""
    if (not isinstance(result, dict) or result.get('consignment_id') != row.consignment_id
            or result.get('merchant_order_id') != row.merchant_order_id):
        raise CourierError('Courier status reference mismatch.')
    status = result.get('order_status_slug') or result.get('order_status')
    if not isinstance(status, str) or not status or len(status) > 100:
        raise CourierError('Courier response has no valid status.')
    row.courier_status = status
    row.state = 'booked'
    row.last_error = ''
    row.save()
    if row.environment != 'live': return
    normalized = status.lower().replace('-', '_').replace(' ', '_')
    shipped = {'picked', 'at_the_sorting_hub', 'in_transit', 'received_at_last_mile_hub', 'assigned_for_delivery', 'delivered'}
    order = Order.objects.get(pk=row.order_id)
    from .commerce import transition_order
    if normalized in shipped and order.status == 'processing':
        order = transition_order(order.pk, 'shipped', actor=row.actor)
        PackagingTask.objects.filter(order=order).update(state='handed_over', handed_at=timezone.now())
    if normalized == 'delivered' and order.status == 'shipped':
        transition_order(order.pk, 'completed', actor=row.actor)
    # Partial delivery, failed delivery and returns remain visible courier exceptions.
    # They never imply payment settlement, cancellation or automatic restocking.


def process_one():
    with transaction.atomic():
        event = CourierEvent.objects.select_for_update(skip_locked=True).filter(processed_at__isnull=True,
            attempts__lt=20, next_attempt_at__lte=timezone.now()).order_by('received_at').first()
        if event is None: return False
        event.attempts += 1
        try:
            # Savepoint rolls back partial status changes if validation fails.
            with transaction.atomic():
                order_id = Shipment.objects.values_list('order_id', flat=True).get(pk=event.shipment_id)
                Order.objects.select_for_update().get(pk=order_id)
                row = Shipment.objects.select_for_update().select_related('account', 'actor').get(pk=event.shipment_id)
                result = adapter(row.account).info(event.consignment_id).get('data')
                if row.consignment_id and row.consignment_id != event.consignment_id:
                    raise CourierError('Courier consignment reference mismatch.')
                row.consignment_id = event.consignment_id
                apply_verified_status(row, result)
                admin.site._registry[Shipment].log_change(_ServiceRequest(row.actor), row, 'Webhook verified against courier API.')
            event.processed_at = timezone.now()
            event.last_error = ''
        except Exception:
            # No upstream body or credential-bearing exception enters the audit directory.
            event.last_error = 'Courier verification failed; retry pending. Check configuration and connectivity.'
            event.next_attempt_at = timezone.now()+timedelta(seconds=min(3600, 30*2**min(event.attempts, 7)))
        event.save()
    return True


class _ServiceRequest:
    def __init__(self, user): self.user = user

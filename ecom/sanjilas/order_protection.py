"""Checkout safeguards; review signals are deliberately separate from proof of fraud."""
import hashlib
import json
import re
import unicodedata
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .models import CommerceBlock, CommerceLimit, Order, SiteSettings


def normalize_phone(value):
    value = ''.join(str(unicodedata.digit(c)) if c.isdigit() else c for c in str(value).strip())
    value = re.sub(r'[\s().-]', '', value)
    if value.startswith('00880'): value = '0' + value[5:]
    elif value.startswith('+880'): value = '0' + value[4:]
    elif value.startswith('880'): value = '0' + value[3:]
    if not re.fullmatch(r'01[0-9]{9}', value):
        raise ValidationError({'phone': 'Enter an 11-digit Bangladesh mobile number, optionally starting with +880.'})
    return value


def identities(user, context, phone=''):
    return {key: str(value) for key, value in {
        'user':user.pk, 'phone':phone, 'browser':context.get('browser_key'), 'ip':context.get('checkout_ip')
    }.items() if value}


def check_blocks(user, context, phone=''):
    query = Q(pk__in=[])
    for kind, value in identities(user, context, phone).items(): query |= Q(kind=kind, value=value)
    if CommerceBlock.objects.filter(query, is_active=True, expires_at__gt=timezone.now()).exists():
        from .commerce import ShopError
        raise ShopError('shop_order_blocked', 403)


def preflight(request, action, phone=''):
    """Committed before stock transactions, so failed attempts also count across workers."""
    site = SiteSettings.load()
    if not site.order_protection_enabled: return
    context = getattr(request, 'commerce_context', {})
    check_blocks(request.user, context, phone)
    limit = site.checkout_attempt_limit if action == 'checkout' else site.reservation_attempt_limit
    now = timezone.now()
    window = int(now.timestamp()) // 600
    keys = sorted(salted_hmac('commerce-limit', f'{action}:{kind}:{value}:{window}', algorithm='sha256').hexdigest()
                  for kind, value in identities(request.user, context, phone).items() if kind != 'ip')
    exceeded = False
    with transaction.atomic():
        for key in keys:
            counter, _ = CommerceLimit.objects.get_or_create(key=key, defaults={'expires_at':now+timedelta(minutes=20)})
            counter = CommerceLimit.objects.select_for_update().get(pk=counter.pk)
            counter.count = min(counter.count + 1, limit + 1)
            counter.save(update_fields=['count'])
            exceeded |= counter.count > limit
    if exceeded:
        from .commerce import ShopError
        raise ShopError('shop_order_limited', 429)


def assess(user, details, rows, site):
    """Called inside checkout, before catalog locks, under shared identity advisory locks."""
    phone = normalize_phone(details['phone'])
    details['phone'] = phone
    details['normalized_phone'] = phone
    if not site.order_protection_enabled: return
    check_blocks(user, details, phone)
    # Serialize different carts sharing identities, not just submissions in one cart.
    for key in sorted(salted_hmac('commerce-checkout-lock', f'{kind}:{value}', algorithm='sha256').hexdigest()
                      for kind,value in identities(user,details,phone).items()):
        lock_id = int.from_bytes(bytes.fromhex(key[:16]), 'big', signed=True)
        with connection.cursor() as cursor: cursor.execute('SELECT pg_advisory_xact_lock(%s)', [lock_id])
    payload = [phone, sorted((row.product_id, row.variant_id or 0, row.quantity) for row in rows)]
    fingerprint = hashlib.sha256(json.dumps(payload).encode()).hexdigest()
    now = timezone.now()
    online = Order.objects.filter(source='online')
    if online.filter(checkout_fingerprint=fingerprint, created_at__gte=now-timedelta(minutes=site.duplicate_order_minutes)).exclude(status='cancelled').exists():
        from .commerce import ShopError
        raise ShopError('shop_duplicate_order')
    reasons = []
    if online.filter(normalized_phone=phone, status__in=['placed','processing','shipped']).count() >= site.order_review_phone_limit:
        reasons.append('open_phone')
    if online.filter(normalized_phone=phone, status='cancelled', created_at__gte=now-timedelta(days=7)).count() >= 3:
        reasons.append('cancelled_phone')
    ip = details.get('checkout_ip')
    if ip and online.filter(checkout_ip=ip, created_at__gte=now-timedelta(hours=1)).count() >= site.order_review_ip_limit:
        reasons.append('busy_ip')
    browser = details.get('browser_key')
    if browser and online.filter(browser_key=browser, created_at__gte=now-timedelta(days=1)).exclude(user=user).values('user_id').distinct().count() >= 2:
        reasons.append('shared_browser')
    details.update(checkout_fingerprint=fingerprint, review_status='pending' if reasons else 'clear', review_reasons=reasons)


def review_data(request, order):
    from django.contrib import admin
    from .operations import allowed
    from .models import OrderReview
    if not request.user.has_perm('sanjilas.review_order'): return None
    ma = admin.site._registry[OrderReview]
    rows = ma.get_queryset(request).filter(order=order).select_related('actor') if allowed(ma,request) else []
    return {'status':order.review_status, 'reasons':order.review_reasons,
            'can_review':order.status in ['placed','processing'] and order.review_status != 'rejected' and allowed(admin.site._registry[Order],request,order,True),
            'history':[{'decision':row.decision,'reason':row.reason,'actor':row.actor.get_username(),'created_at':row.created_at.isoformat()} for row in rows if allowed(ma,request,row)]}


@transaction.atomic
def decide(request, order, decision, reason):
    from django.contrib import admin
    from .models import OrderReview
    from .operations import allowed
    from .commerce import transition_order
    from django.core.exceptions import PermissionDenied
    ma = admin.site._registry[Order]
    order = ma.get_queryset(request).select_for_update().get(pk=order.pk)
    if not request.user.has_perm('sanjilas.review_order') or not allowed(ma,request,order,True): raise PermissionDenied
    if decision not in ['approved','rejected'] or not reason.strip() or len(reason)>500:
        raise ValidationError({'reason':'Enter an approval or rejection reason (maximum 500 characters).'})
    if order.status not in ['placed','processing'] or order.review_status == 'rejected':
        raise ValidationError('This order can no longer be reviewed.')
    if order.review_status == decision: return
    if decision == 'rejected': transition_order(order.pk,'cancelled',actor=request.user)
    Order.objects.filter(pk=order.pk).update(review_status=decision)
    event = OrderReview(order=order,actor=request.user,decision=decision,reason=reason.strip())
    event._review_write = True
    event.save()
    ma.log_change(request,order,f'Order review: {decision}. {reason.strip()}')

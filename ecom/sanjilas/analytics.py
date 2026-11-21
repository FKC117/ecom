"""First-party journey history. Never forward customer contact or browser details."""
import json
from decimal import Decimal
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from .models import CartJourney


def snapshot_journey(cart, currency):
    from .commerce import snapshot
    now = timezone.now()
    lines = list(cart.items.filter(expires_at__gt=now).select_related('product', 'variant'))
    if not lines:
        CartJourney.objects.filter(cart=cart, outcome='open', expires_at__gt=now).update(outcome='emptied')
        return
    expiry = min(line.expires_at for line in lines)
    rows = [snapshot(line, line.product, line.variant) for line in lines]
    # Retain catalog snapshots only, never checkout drafts or customer contact fields.
    CartJourney.objects.update_or_create(cart=cart, expires_at=expiry, defaults={
        'items': json.loads(json.dumps(rows, cls=DjangoJSONEncoder)),
        'subtotal': sum((row['line_total'] or Decimal(0) for row in rows), Decimal(0)),
        'currency': currency, 'outcome': 'open',
    })


def start_checkout(cart, expiry):
    CartJourney.objects.filter(cart=cart, expires_at=expiry, outcome='open', checkout_started_at__isnull=True).update(checkout_started_at=timezone.now())

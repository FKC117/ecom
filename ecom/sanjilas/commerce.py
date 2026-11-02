"""All stock-changing customer operations lock Cart -> Product -> Variant rows."""
import uuid
import hashlib
import json
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from .models import Cart, CartItem, InventoryMovement, Order, OrderItem, Product, ProductVariant, SiteSettings, InvoiceRevision


class ShopError(Exception):
    def __init__(self, key, status=409):
        self.key, self.status = key, status


def reserved_quantity(item, exclude_cart=None):
    query = CartItem.objects.filter(expires_at__gt=timezone.now())
    if isinstance(item, ProductVariant):
        query = query.filter(variant_id=item.pk)
    else:
        query = query.filter(product_id=item.pk, variant__isnull=True)
    if exclude_cart:
        query = query.exclude(cart_id=exclude_cart.pk)
    return query.aggregate(total=Sum('quantity'))['total'] or 0


def available_quantity(item):
    return max(0, item.stock_quantity - reserved_quantity(item)) if item.track_stock else 0


def lock_catalog(lines):
    products = {p.pk:p for p in Product.objects.select_for_update().filter(pk__in=sorted({line.product_id for line in lines if line.product_id})).order_by('pk')}
    variants = {v.pk:v for v in ProductVariant.objects.select_for_update().filter(pk__in=sorted({line.variant_id for line in lines if line.variant_id})).order_by('pk')}
    return products, variants


def target(product, variant):
    if variant:
        if variant.product_id != product.pk or not variant.is_active:
            raise ShopError('shop_unavailable')
        variant.product = product
        return variant
    if product.variants.exists():
        raise ShopError('shop_choose_variant')
    return product


def check_sale(product, item, quantity, cart):
    if not product.is_active or not product.category.is_active or item.discounted_price is None:
        raise ShopError('shop_unavailable')
    if not item.track_stock:
        raise ShopError('shop_stock_unconfigured')
    if item.stock_quantity - reserved_quantity(item, exclude_cart=cart) < quantity:
        raise ShopError('shop_insufficient_stock')
    if product.currency != SiteSettings.load().shop_currency:
        raise ShopError('shop_currency_error')


def get_cart(user):
    return Cart.objects.get_or_create(user=user)[0]


@transaction.atomic
def set_item(user, product_id, variant_id, quantity):
    cart = get_cart(user)
    cart = Cart.objects.select_for_update().get(pk=cart.pk)
    product = Product.objects.select_for_update().filter(pk=product_id).first()
    if not product:
        raise ShopError('shop_unavailable',404)
    variant = ProductVariant.objects.select_for_update().filter(pk=variant_id).first() if variant_id else None
    if variant_id and variant is None:
        raise ShopError('shop_unavailable',404)
    existing = CartItem.objects.filter(cart=cart,product=product,variant_id=variant_id).first()
    if quantity == 0:
        if existing:
            existing.delete()
        if not cart.items.exists():
            cart.checkout_draft={};cart.draft_expires_at=None;cart.save(update_fields=['checkout_draft','draft_expires_at'])
        return cart
    item = target(product,variant)
    check_sale(product,item,quantity,cart)
    now = timezone.now()
    active_expiry=cart.items.filter(expires_at__gt=now).order_by('expires_at').values_list('expires_at',flat=True).first()
    expiry=active_expiry or now+timedelta(minutes=SiteSettings.load().cart_reservation_minutes)
    CartItem.objects.update_or_create(cart=cart,product=product,variant=variant,defaults={'quantity':quantity,'expires_at':expiry})
    return cart


def snapshot(line, product, variant):
    item = variant or product
    if variant:
        variant.product = product
    image = item.image or product.image
    return {'product_id': product.pk, 'variant_id': variant.pk if variant else None,
            'product_name': product.name, 'variant_name': variant.name if variant else '',
            'sku': item.sku or '', 'quantity': line.quantity,
            'discount_mode':'fixed','discount_input':item.regular_price-item.discounted_price if item.regular_price is not None else Decimal(0),
            'regular_price': item.regular_price, 'unit_price': item.discounted_price,
            'line_total': item.discounted_price * line.quantity if item.discounted_price is not None else None,
            'image_url': image.url if image else ''}


def checkout_quote(rows, currency, shipping_fee):
    def money(value):
        return str(Decimal(value).quantize(Decimal('.01'))) if value is not None else None
    payload = {'currency':currency,'shipping':money(shipping_fee),'items':[
        [row['product_id'],row['variant_id'],row['quantity'],money(row['regular_price']),money(row['unit_price'])] for row in rows]}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


@transaction.atomic
def place_order(user, key, details, quote=None):
    cart = get_cart(user)
    cart = Cart.objects.select_for_update().get(pk=cart.pk)
    existing = Order.objects.filter(checkout_key=key).first()
    if existing:
        if existing.user_id != user.pk:
            raise ShopError('shop_checkout_conflict')
        return existing
    site = SiteSettings.load()
    method=details.get('payment_method') or 'cod'
    if method=='cod' and not site.cash_on_delivery_enabled:raise ShopError('shop_payment_unavailable')
    if method not in ['cod','delivery_advance','pay_now']:raise ShopError('shop_payment_unavailable')
    if method=='pay_now' and not site.dummy_payments_enabled:raise ShopError('shop_payment_unavailable')
    if method=='delivery_advance' and not site.dummy_payments_enabled and (not site.delivery_advance_enabled or not site.delivery_advance_instructions.strip() or details.get('advance_channel') not in site.delivery_advance_methods or details.get('advance_channel') not in ['bkash','nagad','bank'] or not str(details.get('advance_reference','')).strip()):raise ShopError('shop_payment_unavailable')
    details={**details,'payment_method':method}
    if method=='cod':details.update(advance_reference='',advance_channel='')
    lines = list(cart.items.all())
    if not lines:
        raise ShopError('shop_empty')
    products, variants = lock_catalog(lines)
    now = timezone.now()
    if any(line.expires_at <= now for line in lines):
        raise ShopError('shop_expired')
    snapshots = []
    for line in lines:
        product, variant = products[line.product_id], variants.get(line.variant_id)
        item = target(product,variant)
        check_sale(product,item,line.quantity,cart)
        snapshots.append(snapshot(line,product,variant))
    from .delivery import charge
    details={**details,'delivery_zone':details.get('delivery_zone') or 'inside'}
    shipping=charge(site,details['delivery_zone'])
    details['advance_amount']=shipping if method=='delivery_advance' else Decimal(0)
    if method=='delivery_advance' and shipping<=0:raise ShopError('shop_payment_unavailable')
    if quote is not None and quote != checkout_quote(snapshots,site.shop_currency,shipping):
        raise ShopError('shop_price_changed')
    subtotal = sum((row['line_total'] for row in snapshots),Decimal(0))
    order = Order(user=user, checkout_key=key, currency=site.shop_currency, subtotal=subtotal,
                  shipping_fee=shipping, total=subtotal+shipping, **details)
    order.full_clean()
    order._commerce_write = True
    order.save()
    for line, row in zip(lines,snapshots):
        OrderItem.objects.create(order=order,**row)
        item = variants.get(line.variant_id) or products[line.product_id]
        type(item).objects.filter(pk=item.pk).update(stock_quantity=F('stock_quantity')-line.quantity)
        InventoryMovement.objects.create(product_id=line.product_id,variant_id=line.variant_id,order=order,quantity=-line.quantity,reason='sale',actor=user)
    if site.dummy_payments_enabled and method in ['delivery_advance','pay_now']:
        from . import payments
        from .models import OrderPayment
        from types import SimpleNamespace
        order.advance_reference='DUMMY-'+str(key)
        order.advance_channel='dummy'
        order._commerce_write=True;order.save()
        amount=shipping if method=='delivery_advance' else order.total
        from .shop import labels
        payments.append(SimpleNamespace(user=user),order,OrderPayment(kind='payment',amount=amount,method='dummy',is_simulated=True,reference=order.advance_reference,notes=labels()['dummy_payment_note']),uuid.uuid5(key,'dummy-payment'))
    cart.items.all().delete()
    cart.checkout_draft={};cart.draft_expires_at=None;cart.save(update_fields=['checkout_draft','draft_expires_at'])
    return order


@transaction.atomic
def transition_order(order_id, status, user=None, actor=None):
    order = Order.objects.select_for_update().get(pk=order_id)
    if user is not None and (order.user_id != user.pk or (order.status != 'placed' and order.status != status)):
        raise ShopError('shop_cancel_denied',403)
    if order.status == status:
        return order
    allowed = {'placed': {'processing','cancelled'}, 'processing': {'shipped','cancelled'}, 'shipped': {'completed'}, 'completed': set(), 'cancelled': set()}
    if status not in allowed[order.status]:
        raise ValidationError({'status':'This order status transition is not allowed.'})
    from .invoice_edits import snapshot
    before=snapshot(order)
    if status == 'cancelled':
        lines = list(order.items.all())
        products,variants = lock_catalog(lines)
        for line in lines:
            if not line.product_id:
                continue
            item = variants.get(line.variant_id) or products[line.product_id]
            type(item).objects.filter(pk=item.pk).update(stock_quantity=F('stock_quantity')+line.quantity)
            InventoryMovement.objects.create(product_id=line.product_id,variant_id=line.variant_id,order=order,quantity=line.quantity,reason='cancellation',actor=actor or user)
    order.status = status
    from .payments import summary
    order.payment_status=summary(order)['payment_status']
    order.revision+=1
    order._commerce_write = True
    order.save(update_fields=['status','revision'])
    InvoiceRevision.objects.create(order=order,version=order.revision,actor=actor or user,reason=f"Status: {order.get_status_display()}",before=before,after=snapshot(order))
    return order

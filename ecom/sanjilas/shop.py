"""Session-authenticated storefront cart/order endpoints; every write uses CSRF."""
from . import payments
from functools import wraps

from django import forms
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from . import commerce
from .models import Cart, HomePage, Order, SiteSettings
from .shop_copy import shop_labels


def labels():
    page = HomePage.objects.filter(pk=1).first()
    from .models import homepage_labels
    return {**homepage_labels(), **(page.labels if page else {})}


def fail(key, status=400, **extra):
    return JsonResponse({'error':labels()[key], **extra},status=status)


def customer(view):
    @never_cache
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_active:
            return fail('shop_login_required',401)
        try:
            return view(request,*args,**kwargs)
        except commerce.ShopError as error:
            return fail(error.key,error.status)
        except ValidationError as error:
            return fail('shop_invalid',400,errors=getattr(error,'message_dict',{'__all__':error.messages}))
        except (ValueError, TypeError, IntegrityError):
            return fail('shop_invalid')
    return wrapped


@transaction.atomic
def order_data(order):
    order=Order.objects.select_for_update().get(pk=order.pk)
    return {'id':str(order.pk),'reference':order.reference,'status':order.status,'created_at':order.created_at.isoformat(),
            'currency':order.currency,'subtotal':order.subtotal,'shipping_fee':order.shipping_fee,'total':order.total,
            'payment_method':order.payment_method,'advance_pending':order.payment_method=='delivery_advance' and not order.advance_verified,'advance_reference':order.advance_reference,'advance_amount':order.advance_amount,'advance_channel':order.advance_channel,**payments.summary(order),'payments':[{k:v for k,v in row.items() if k not in ['actor','notes','reference']} for row in payments.entries(order)],'delivery_zone':order.delivery_zone,
            'items':list(order.items.values('product_name','variant_name','sku','quantity','regular_price','unit_price','line_total','image_url'))}


def cart_data(user,zone="inside"):
    from .delivery import charge,rates
    site = SiteSettings.load()
    shipping=charge(site,zone)
    cart = Cart.objects.filter(user=user).first()
    rows=[]
    if cart:
        for line in cart.items.select_related('product__collection','variant'):
            product,variant=line.product,line.variant
            item=variant or product
            row=commerce.snapshot(line,product,variant)
            row.update(id=line.pk,expires_at=line.expires_at.isoformat(),expired=line.expires_at<=timezone.now(),
                       currency=product.currency,max_quantity=max(0,item.stock_quantity-commerce.reserved_quantity(item,exclude_cart=cart)))
            rows.append(row)
    active=[row for row in rows if not row['expired']]
    subtotal=sum((row['line_total'] or 0 for row in active),0)
    return {'quote':commerce.checkout_quote(rows,site.shop_currency,shipping),'items':rows,'subtotal':subtotal,'shipping_fee':shipping if active else 0,'delivery_zone':zone,'delivery_rates':rates(site),
            'total':subtotal+shipping if active else 0,'currency':site.shop_currency,
            'dummy_enabled':site.dummy_payments_enabled,'pay_now_enabled':site.dummy_payments_enabled,'cod_enabled':site.cash_on_delivery_enabled,'advance_enabled':site.dummy_payments_enabled or site.delivery_advance_enabled and bool(site.delivery_advance_instructions.strip()) and bool([m for m in site.delivery_advance_methods if m in ['bkash','nagad','bank']]),'advance_instructions':site.delivery_advance_instructions,'advance_methods':[m for m in site.delivery_advance_methods if m in ['bkash','nagad','bank']],'server_time':timezone.now().isoformat()}


@never_cache
@ensure_csrf_cookie
@require_GET
def cart(request):
    authenticated=request.user.is_authenticated and request.user.is_active
    return JsonResponse({'authenticated':authenticated,'csrf_token':get_token(request),'labels':labels(),
                         **(cart_data(request.user,request.session.get("delivery_zone","inside")) if authenticated else {'items':[]})})


@customer
@require_POST
def cart_item(request):
    product=int(request.POST.get('product_id',''))
    variant=int(request.POST['variant_id']) if request.POST.get('variant_id') else None
    quantity=int(request.POST.get('quantity',''))
    if not 0<=quantity<=999:
        return fail('shop_invalid')
    commerce.set_item(request.user,product,variant,quantity)
    return JsonResponse(cart_data(request.user,request.session.get("delivery_zone","inside")))


class CheckoutForm(forms.Form):
    checkout_key=forms.UUIDField()
    quote=forms.CharField(min_length=64,max_length=64)
    customer_name=forms.CharField(max_length=150)
    email=forms.EmailField(required=False)
    phone=forms.CharField(max_length=40)
    address=forms.CharField(max_length=1000)
    area=forms.CharField(max_length=150)
    city=forms.CharField(max_length=120)
    postal_code=forms.CharField(max_length=30,required=False)
    notes=forms.CharField(max_length=1000,required=False)
    payment_method=forms.ChoiceField(choices=[('cod','Cash on delivery'),('delivery_advance','Delivery charge in advance'),('pay_now','Pay now')],required=False)
    advance_reference=forms.CharField(max_length=150,required=False)
    advance_channel=forms.ChoiceField(choices=[('bkash','bKash'),('nagad','Nagad'),('bank','Bank transfer')],required=False)
    delivery_zone=forms.ChoiceField(choices=[("inside","Inside Dhaka"),("outside","Outside Dhaka")],required=False)


@customer
@require_POST
def checkout(request):
    form=CheckoutForm(request.POST)
    if not form.is_valid():
        return fail('shop_invalid',errors={key:list(values) for key,values in form.errors.items()})
    details=dict(form.cleaned_data)
    key=details.pop('checkout_key')
    quote=details.pop('quote')
    details['delivery_zone']=details.get('delivery_zone') or request.session.get('delivery_zone','inside')
    order=commerce.place_order(request.user,key,details,quote=quote)
    return JsonResponse({'order':order_data(order),'cart':cart_data(request.user)})


@customer
@require_GET
def orders(request):
    return JsonResponse({'orders':[order_data(order) for order in Order.objects.filter(user=request.user).prefetch_related('items')[:50]]})


@customer
@require_POST
def cancel(request, order_id):
    if not Order.objects.filter(pk=order_id,user=request.user).exists():
        return fail('shop_unavailable',404)
    order=commerce.transition_order(order_id,'cancelled',user=request.user)
    return JsonResponse({'order':order_data(order)})


@customer
@require_GET
@transaction.atomic
def invoice(request, order_id):
    from django.contrib import admin
    from .control import active_operator, permissions
    from .models import OrderItem
    from .branding import public_settings
    order=Order.objects.select_for_update().filter(pk=order_id,user=request.user).first()
    if order is None:
        ma=admin.site._registry[Order]
        if not active_operator(request.user) or not ma.has_module_permission(request) or not permissions(ma,request)['view']:
            return fail('shop_unavailable',404)
        order=ma.get_queryset(request).select_for_update().filter(pk=order_id).first()
        if order is None or not permissions(ma,request,order)['view']:
            return fail('shop_unavailable',404)
        item_admin=admin.site._registry[OrderItem]
        if not item_admin.has_module_permission(request) or not permissions(item_admin,request)['view']:
            return fail('shop_unavailable',404)
        visible=list(item_admin.get_queryset(request).filter(order=order))
        if len(visible)!=order.items.count() or any(not permissions(item_admin,request,item)['view'] for item in visible):
            return fail('shop_unavailable',404)
    data=order_data(order)
    data.update(invoice_reference=order.reference.replace('ORD-','INV-',1),customer=order.customer_name,
                email=order.email,phone=order.phone,address=order.address,area=order.area,city=order.city,postal_code=order.postal_code)
    for row in data['items']:
        row['discount_amount']=(row['regular_price']-row['unit_price'])*row['quantity']
    data['discount_total']=sum((item.regular_price-item.unit_price)*item.quantity for item in order.items.all())
    data['regular_subtotal']=sum(item.regular_price*item.quantity for item in order.items.all())
    return JsonResponse({'order':data,'site':public_settings(SiteSettings.load(),request),'labels':labels()})


@customer
@require_POST
def delivery_area(request):
    zone=request.POST.get('delivery_zone')
    if zone not in ['inside','outside']:return fail('shop_invalid')
    request.session['delivery_zone']=zone
    return JsonResponse(cart_data(request.user,zone))

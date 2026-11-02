"""Staff-only manual invoicing; catalog stock uses the checkout locking order."""
import hashlib
import json
from decimal import Decimal
from types import SimpleNamespace

from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.models import F, Sum
from django.views.decorators.http import require_GET, require_POST

from . import control, commerce
from .models import Order, OrderItem, Product, ProductVariant, InventoryMovement, SiteSettings
from .operations import allowed
from .delivery import rates
from .locations import directory


def permitted(request):
    return request.user.has_perm('sanjilas.create_manual_invoice') and allowed(admin.site._registry[Order],request,write=True) and allowed(admin.site._registry[OrderItem],request)


class HeaderForm(forms.Form):
    checkout_key=forms.UUIDField()
    customer_name=forms.CharField(max_length=150)
    email=forms.EmailField(required=False)
    phone=forms.CharField(max_length=40,required=False)
    address=forms.CharField(max_length=1000,required=False)
    area=forms.CharField(max_length=150,required=False)
    city=forms.CharField(max_length=120,required=False)
    postal_code=forms.CharField(max_length=30,required=False)
    notes=forms.CharField(max_length=1000,required=False)
    shipping_fee=forms.DecimalField(max_digits=12,decimal_places=2,min_value=0)
    delivery_zone=forms.ChoiceField(choices=[('inside','Inside Dhaka'),('outside','Outside Dhaka'),('custom','Custom charge')],required=False)
    items=forms.JSONField()


class CustomLineForm(forms.Form):
    name=forms.CharField(max_length=200)
    sku=forms.CharField(max_length=80,required=False)
    price=forms.DecimalField(max_digits=12,decimal_places=2,min_value=0)
    discount=forms.DecimalField(max_digits=12,decimal_places=2,min_value=0,initial=0)

    def clean(self):
        data=super().clean()
        if data.get('price') is not None and data.get('discount') is not None and data['discount']>data['price']:
            raise ValidationError('Discount cannot exceed the unit price.')
        return data


def manual_discount(line, price, default_type='fixed'):
    kind=line.get('discount_type',default_type)
    if kind not in ['fixed','percent']:
        raise ValidationError({'items':control.labels()['invalid_form']})
    field=forms.DecimalField(max_digits=12,decimal_places=2,min_value=0)
    value=field.clean(line.get('discount',0))
    if kind=='percent':
        if value>100:raise ValidationError({'items':control.labels()['manual_discount_invalid']})
        from decimal import ROUND_HALF_UP
        value=price-(price*(Decimal(100)-value)/Decimal(100)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    if value>price:raise ValidationError({'items':control.labels()['manual_discount_invalid']})
    return value


def accessible(request,obj):
    ma=admin.site._registry[type(obj)]
    return allowed(ma,request,obj) and ma.get_queryset(request).filter(pk=obj.pk).exists()


@control.operator_required
@require_GET
def catalog(request):
    if not permitted(request) and not (request.user.has_perm('sanjilas.edit_invoice') and allowed(admin.site._registry[Order],request,write=True) and allowed(admin.site._registry[OrderItem],request)): raise PermissionDenied
    term=request.GET.get('q','').strip().casefold()[:120]
    rows=[]
    for model in [Product,ProductVariant]:
        ma=admin.site._registry[model]
        if not allowed(ma,request): continue
        qs=ma.get_queryset(request)
        qs=qs.filter(variants__isnull=True) if model is Product else qs.select_related('product')
        for item in qs:
            if not allowed(ma,request,item): continue
            product=item if model is Product else item.product
            if not product.is_active or not product.category.is_active or not item.is_active:continue
            name=product.name if model is Product else f'{product.name} / {item.name}'
            if term and term not in f'{name} {item.sku or ""}'.casefold():continue
            rows.append({'id':item.pk,'model':item._meta.model_name,'name':name,'sku':item.sku or '',
                         'price':item.discounted_price,'regular_price':item.regular_price,'catalog_discount_type':item.discount_source.discount_type,'catalog_discount_value':item.discount_source.discount_value,'discount_amount':item.regular_price-item.discounted_price if item.regular_price is not None else 0,'currency':product.currency,'available':commerce.available_quantity(item)})
            if len(rows)>=50:break
    site=SiteSettings.load()
    return control.JsonResponse({'items':rows[:50],'currency':site.shop_currency,'shipping_fee':site.shipping_fee,'delivery_rates':rates(site),'can_record_payment':request.user.has_perm('sanjilas.mark_payment'),'locations':directory()})


@transaction.atomic
def build(request,post,issue=False,editing=None):
    if editing is None and not permitted(request):raise PermissionDenied
    form=HeaderForm(post)
    if not form.is_valid():raise ValidationError({key:list(values) for key,values in form.errors.items()})
    values=dict(form.cleaned_data)
    key=values.pop('checkout_key');lines=values.pop('items');shipping=values.pop('shipping_fee')
    from .delivery import charge
    values['delivery_zone']=values.get('delivery_zone') or 'custom'
    shipping=charge(SiteSettings.load(),values['delivery_zone'],shipping)
    from .locations import resolve
    if editing is None or values['city']!=editing.city or values['area']!=editing.area:
        values.update(resolve(values['city'],values['area'],required=False))
    if not isinstance(lines,list) or not 1<=len(lines)<=50:raise ValidationError({'items':control.labels()['manual_items_required']})
    if editing is None:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)',[key.int & ((1<<63)-1)])
    if issue:
        existing=Order.objects.filter(checkout_key=key).first()
        if existing:
            if existing.source!='manual' or existing.created_by_id!=request.user.pk or not accessible(request,existing):raise PermissionDenied
            return {'id':str(existing.pk),'reference':existing.reference}
    normalized=[];identities=set()
    for line in lines:
        if not isinstance(line,dict):raise ValidationError({'items':control.labels()['invalid_form']})
        quantity=line.get('quantity')
        if isinstance(quantity,bool) or not isinstance(quantity,int) or not 1<=quantity<=999:raise ValidationError({'items':control.labels()['manual_quantity_error']})
        kind=line.get('model')
        if kind=='custom':normalized.append((line,quantity,None));continue
        if kind not in ['product','productvariant'] or isinstance(line.get('id'),bool) or not isinstance(line.get('id'),int):raise ValidationError({'items':control.labels()['invalid_form']})
        identity=(kind,line['id'])
        if identity in identities:raise ValidationError({'items':control.labels()['manual_duplicate']})
        identities.add(identity)
        model=Product if kind=='product' else ProductVariant
        ma=admin.site._registry[model]
        if not allowed(ma,request):raise PermissionDenied
        item=ma.get_queryset(request).filter(pk=line['id']).first()
        if item is None or not allowed(ma,request,item):raise PermissionDenied
        normalized.append((line,quantity,item))
    lock_lines=[SimpleNamespace(product_id=item.pk if isinstance(item,Product) else item.product_id,variant_id=item.pk if isinstance(item,ProductVariant) else None) for _,_,item in normalized if item is not None]
    products,variants=commerce.lock_catalog(lock_lines)
    snapshots=[]
    try:
        for line,quantity,original in normalized:
            if original is None:
                custom=CustomLineForm({'name':line.get('name'),'sku':line.get('sku',''),'price':line.get('price'),'discount':0})
                if not custom.is_valid():raise ValidationError({'items':[message for values in custom.errors.values() for message in values]})
                c=custom.cleaned_data
                c['discount']=manual_discount(line,c['price'])
                snapshots.append({'product_id':None,'variant_id':None,'product_name':c['name'],'variant_name':'','sku':c['sku'],'quantity':quantity,'discount_mode':line.get('discount_type','fixed'),'discount_input':Decimal(str(line.get('discount',0))),'regular_price':c['price'],'unit_price':c['price']-c['discount'],'line_total':(c['price']-c['discount'])*quantity,'image_url':''})
            else:
                product=products[original.pk if isinstance(original,Product) else original.product_id]
                variant=variants.get(original.pk) if isinstance(original,ProductVariant) else None
                existing=editing.items.filter(product_id=product.pk,variant_id=variant.pk if variant else None).aggregate(total=Sum('quantity'))['total'] if editing else 0
                item=variant or product
                if variant:variant.product=product
                if not existing:item=commerce.target(product,variant)
                if not accessible(request,item):raise PermissionDenied
                if editing is None:
                    commerce.check_sale(product,item,quantity,None)
                elif editing.status!='cancelled' and (item.stock_quantity-commerce.reserved_quantity(item)<quantity or (quantity>(existing or 0) and (not item.track_stock or not item.is_active or not product.is_active))):
                    raise ValidationError({'items':control.labels()['invoice_edit_stock']})
                row=commerce.snapshot(SimpleNamespace(quantity=quantity),product,variant)
                if editing is not None:
                    row['regular_price']=forms.DecimalField(max_digits=12,decimal_places=2,min_value=0).clean(line.get('regular_price',row['regular_price']))
                if editing is not None and line.get('discount_type','catalog')=='catalog':
                    source=item.discount_source
                    discount=manual_discount({'discount_type':'percent' if source.discount_type=='percent' else 'fixed','discount':source.discount_value if source.discount_type!='none' else 0},row['regular_price'])
                    row['unit_price']=row['regular_price']-discount;row['line_total']=row['unit_price']*quantity
                if line.get('discount_type','catalog')!='catalog':
                    discount=manual_discount(line,row['regular_price'])
                    row['unit_price']=row['regular_price']-discount
                    row['line_total']=row['unit_price']*quantity
                row['discount_mode']=line.get('discount_type','catalog') if line.get('discount_type','catalog')!='catalog' else 'fixed'
                row['discount_input']=Decimal(str(line.get('discount',0))) if line.get('discount_type','catalog')!='catalog' else row['regular_price']-row['unit_price']
                if editing is not None:
                    row['product_name']=forms.CharField(max_length=200).clean(line.get('invoice_name',row['product_name']))
                    row['variant_name']=forms.CharField(max_length=150,required=False).clean(line.get('invoice_variant',row['variant_name']))
                    row['sku']=forms.CharField(max_length=80,required=False).clean(line.get('sku',row['sku']))
                snapshots.append(row)
    except commerce.ShopError as error:
        from .shop import labels
        raise ValidationError({'items':labels()[error.key]})
    site=SiteSettings.load()
    currency=editing.currency if editing is not None else site.shop_currency
    subtotal=sum((row['line_total'] for row in snapshots),Decimal(0));total=subtotal+shipping
    from . import payments
    paid=forms.DecimalField(max_digits=14,decimal_places=2,min_value=0).clean(post.get('amount_paid') or '0')
    advance=None
    if paid:
        if editing is not None:raise ValidationError(control.labels()['payment_use_ledger'])
        if not request.user.has_perm('sanjilas.mark_payment'):raise PermissionDenied
        if paid>total:raise ValidationError({'amount_paid':control.labels()['payment_excess']})
        payment_form=payments.PaymentForm({'kind':'payment','amount':paid,'method':post.get('payment_method'),
            'reference':post.get('payment_reference',''),'occurred_at':post.get('payment_date'),
            'notes':post.get('payment_notes') or control.labels()['manual_advance_note']})
        if not payment_form.is_valid():raise ValidationError({k:list(v) for k,v in payment_form.errors.items()})
        advance=dict(payment_form.cleaned_data)
        from django.utils import timezone
        if advance['occurred_at']>timezone.now():raise ValidationError(control.labels()['payment_future'])
    quote=hashlib.sha256(json.dumps({'details':{k:v for k,v in values.items() if k not in ['city_record','area_record']},'lines':snapshots,'currency':currency,'shipping':shipping,'advance':advance},sort_keys=True,default=str).encode()).hexdigest()
    if not issue:return {'amount_paid':paid,'amount_due':total-paid,'advance':advance,'line_discounts':[(row['regular_price']-row['unit_price'])*row['quantity'] for row in snapshots],'discount_total':sum((row['regular_price']-row['unit_price'])*row['quantity'] for row in snapshots),'quote':quote,'details':{k:v for k,v in values.items() if k not in ['city_record','area_record']},'items':snapshots,'regular_subtotal':sum(row['regular_price']*row['quantity'] for row in snapshots),'subtotal':subtotal,'shipping_fee':shipping,'total':total,'currency':currency}
    if post.get('quote')!=quote:raise ValidationError({'items':control.labels()['manual_review_changed']})
    order=Order(user=None,created_by=request.user,source='manual',checkout_key=key,currency=site.shop_currency,subtotal=subtotal,shipping_fee=shipping,total=total,**values)
    order.full_clean();order._commerce_write=True;order.save()
    for row in snapshots:
        created_item=OrderItem.objects.create(order=order,**row)
        if not accessible(request,created_item):raise PermissionDenied
        if row['product_id']:
            item=variants.get(row['variant_id']) or products[row['product_id']]
            type(item).objects.filter(pk=item.pk).update(stock_quantity=F('stock_quantity')-row['quantity'])
            InventoryMovement.objects.create(product_id=row['product_id'],variant_id=row['variant_id'],order=order,quantity=-row['quantity'],reason='sale',actor=request.user,note=control.labels()['manual_title'])
    if not accessible(request,order):raise PermissionDenied
    if advance:
        from .models import OrderPayment
        import uuid
        payments.append(request,order,OrderPayment(**advance),uuid.uuid5(key,'initial-payment'))
    admin.site._registry[Order].log_addition(request,order,control.labels()['manual_title'])
    return {'id':str(order.pk),'reference':order.reference}


@control.operator_required
@require_POST
def preview(request):return control.JsonResponse(build(request,request.POST))


@control.operator_required
@require_POST
def issue(request):return control.JsonResponse(build(request,request.POST,issue=True))

"""Transactional invoice amendments with immutable before/after snapshots."""
from . import payments
import hashlib
import uuid
from collections import Counter
from types import SimpleNamespace
from decimal import Decimal

from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET,require_POST

from . import control,commerce,manual_invoices
from .models import Order,OrderItem,InvoiceRevision,InventoryMovement,Product,ProductVariant
from .operations import allowed


def snapshot(order):
    return {'reference':order.reference,'advance_verified':order.advance_verified,**{k:str(v) for k,v in payments.summary(order).items()},'delivery_zone':order.delivery_zone,'status':order.status,'currency':order.currency,
        'customer_name':order.customer_name,'email':order.email,'phone':order.phone,'address':order.address,
        'area':order.area,'city':order.city,'postal_code':order.postal_code,'notes':order.notes,
        'subtotal':str(order.subtotal),'shipping_fee':str(order.shipping_fee),'total':str(order.total),
        'items':[{key:str(getattr(item,key)) if key in ['regular_price','unit_price','line_total','discount_input'] else getattr(item,key)
                  for key in ['product_id','variant_id','product_name','variant_name','sku','quantity','regular_price','unit_price','line_total','discount_mode','discount_input','image_url']} for item in order.items.order_by('pk')]}


def can_edit(request,order):
    if not request.user.has_perm('sanjilas.edit_invoice') or not manual_invoices.accessible(request,order) or not allowed(admin.site._registry[Order],request,order,True):return False
    ma=admin.site._registry[OrderItem]
    return allowed(ma,request) and all(manual_invoices.accessible(request,item) for item in order.items.all())


def scoped_order(request,pk,write=False):
    ma=admin.site._registry[Order]
    order=get_object_or_404(ma.get_queryset(request).select_for_update() if write else ma.get_queryset(request),pk=pk)
    if not can_edit(request,order):raise PermissionDenied
    return order


@control.operator_required
@require_GET
def detail(request,pk):
    order=scoped_order(request,pk)
    lines=[]
    for item in order.items.order_by('pk'):
        row={'model':'productvariant' if item.variant_id else 'product' if item.product_id else 'custom',
             'id':item.variant_id or item.product_id,'name':item.product_name,'invoice_name':item.product_name,
             'invoice_variant':item.variant_name,'sku':item.sku,'regular_price':item.regular_price,'price':item.regular_price,
             'quantity':item.quantity,'discount_type':item.discount_mode,'discount':item.discount_input}
        if item.product_id:
            catalog=item.variant or item.product
            row.update(catalog_price=catalog.discounted_price,discount_amount=(catalog.regular_price-catalog.discounted_price) if catalog.regular_price is not None else 0,
                       catalog_regular_price=catalog.regular_price,catalog_discount_type=catalog.discount_source.discount_type,catalog_discount_value=catalog.discount_source.discount_value)
        lines.append(row)
    return control.JsonResponse({'id':str(order.pk),'reference':order.reference,'version':order.revision,
        'details':{name:getattr(order,name) for name in ['customer_name','email','phone','address','area','city','postal_code','notes','shipping_fee','delivery_zone']},'items':lines,'currency':order.currency})


@transaction.atomic
def amend(request,pk,post,save=False):
    order=scoped_order(request,pk,True)
    try:key=uuid.UUID(post.get('checkout_key',''));expected=int(post.get('expected_version',''))
    except (ValueError,TypeError):raise ValidationError(control.labels()['invalid_form'])
    previous=InvoiceRevision.objects.filter(operation_key=key).first()
    if previous:
        if previous.order_id!=order.pk or previous.actor_id!=request.user.pk:raise PermissionDenied
        return {'id':str(order.pk),'reference':order.reference}
    if expected!=order.revision:raise ValidationError(control.labels()['invoice_stale'])
    reason=forms.CharField(max_length=500).clean(post.get('edit_reason',''))
    before=snapshot(order)
    old_lines=list(order.items.all())
    try:
        import json
        proposed=json.loads(post.get('items','[]'))
        if not isinstance(proposed,list):raise ValueError
        new_locks=[]
        for row in proposed:
            if not isinstance(row,dict):raise ValueError
            if row.get('model')=='product':new_locks.append(SimpleNamespace(product_id=int(row['id']),variant_id=None))
            elif row.get('model')=='productvariant':
                ma=admin.site._registry[ProductVariant]
                variant=get_object_or_404(ma.get_queryset(request),pk=int(row['id']))
                new_locks.append(SimpleNamespace(product_id=variant.product_id,variant_id=variant.pk))
    except (ValueError,TypeError,KeyError):raise ValidationError(control.labels()['invalid_form'])
    products,variants=commerce.lock_catalog(old_lines+new_locks)
    old_counts=Counter()
    for row in old_lines:
        if row.product_id:old_counts[(row.product_id,row.variant_id)]+=row.quantity
    savepoint=transaction.savepoint()
    if order.status!='cancelled':
        for (product_id,variant_id),quantity in old_counts.items():
            item=variants.get(variant_id) or products[product_id]
            type(item).objects.filter(pk=item.pk).update(stock_quantity=F('stock_quantity')+quantity)
    reviewed=manual_invoices.build(request,post,editing=order)
    quote=hashlib.sha256(f"{reviewed['quote']}:{order.pk}:{order.revision}:{reason}".encode()).hexdigest()
    if not save:
        transaction.savepoint_rollback(savepoint)
        return {**reviewed,'quote':quote}
    if post.get('quote')!=quote:raise ValidationError(control.labels()['manual_review_changed'])
    new_counts=Counter()
    for row in reviewed['items']:
        if row['product_id']:new_counts[(row['product_id'],row['variant_id'])]+=row['quantity']
    if order.status!='cancelled':
        for (product_id,variant_id),quantity in new_counts.items():
            item=variants.get(variant_id) or products[product_id]
            type(item).objects.filter(pk=item.pk).update(stock_quantity=F('stock_quantity')-quantity)
        for identity in old_counts.keys()|new_counts.keys():
            delta=old_counts[identity]-new_counts[identity]
            if delta:InventoryMovement.objects.create(product_id=identity[0],variant_id=identity[1],order=order,quantity=delta,reason='adjustment',actor=request.user,note=reason)
    if reviewed['details']['city']!=order.city or reviewed['details']['area']!=order.area:
        from .locations import resolve
        for name,value in resolve(reviewed['details']['city'],reviewed['details']['area'],required=False).items():setattr(order,name,value)
    for name,value in reviewed['details'].items():setattr(order,name,value)
    order.subtotal=reviewed['subtotal'];order.shipping_fee=reviewed['shipping_fee'];order.total=reviewed['total'];order.revision+=1
    order.payment_status=payments.summary(order)['payment_status']
    order.full_clean();order._commerce_write=True;order.save()
    order.items.all().delete()
    for row in reviewed['items']:OrderItem.objects.create(order=order,**row)
    after=snapshot(order)
    InvoiceRevision.objects.create(order=order,version=order.revision,operation_key=key,actor=request.user,reason=reason,before=before,after=after)
    admin.site._registry[Order].log_change(request,order,reason)
    return {'id':str(order.pk),'reference':order.reference}


@control.operator_required
@require_POST
def preview(request,pk):return control.JsonResponse(amend(request,pk,request.POST))


@control.operator_required
@require_POST
def save(request,pk):return control.JsonResponse(amend(request,pk,request.POST,save=True))


@control.operator_required
@require_GET
def history(request,pk):
    order=get_object_or_404(admin.site._registry[Order].get_queryset(request),pk=pk)
    ma=admin.site._registry[InvoiceRevision]
    if not allowed(admin.site._registry[Order],request,order) or not allowed(ma,request):raise PermissionDenied
    return control.JsonResponse({'reference':order.reference,'rows':[{'version':row.version,'actor':row.actor.get_username() if row.actor_id else '', 'reason':row.reason,'created_at':row.created_at.isoformat(),'before':row.before,'after':row.after}
        for row in ma.get_queryset(request).filter(order=order).select_related('actor') if allowed(ma,request,row)]})

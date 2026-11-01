"""Operational views use the registered ModelAdmin querysets, forms and permissions."""
from . import payments
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum, OuterRef, Subquery, IntegerField
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import control
from .models import Product, ProductVariant, CartItem, Order, InventoryMovement, SiteSettings


def allowed(ma, request, obj=None, write=False):
    return ma.has_module_permission(request) and control.permissions(ma,request,obj)['change' if write else 'view']


def directory(request):
    from .manual_invoices import permitted
    result=[]
    for key,models,label in [('orders',[Order],'ops_orders'),('stock',[Product,ProductVariant],'ops_stock')]:
        if any(allowed(admin.site._registry[model],request) for model in models):
            result.append({'key':key,'name':control.labels()[label],'can_create':key=='orders' and permitted(request)})
    return result


def page_data(rows, request):
    page=Paginator(rows,20).get_page(request.GET.get('page',1))
    return page,{'page':page.number,'pages':page.paginator.num_pages,'count':page.paginator.count}


@control.operator_required
@require_GET
def orders(request):
    ma=admin.site._registry[Order]
    if not allowed(ma,request): raise PermissionDenied
    qs=ma.get_queryset(request)
    term=request.GET.get('q','').strip()[:120]
    if term:
        query=Q(customer_name__icontains=term)|Q(email__icontains=term)|Q(phone__icontains=term)
        number=term.upper().removeprefix('ORD-')
        if term.upper().startswith('ORD-') and '-' in number:
            suffix=number.rsplit('-',1)[-1]
            number=str(int(suffix)-100000) if suffix.isdigit() else ''
        if number.isdigit(): query|=Q(reference_number=int(number))
        qs=qs.filter(query)
    visible=[obj for obj in qs if allowed(ma,request,obj)]
    counts={value:sum(obj.status==value for obj in visible) for value,_ in Order.Status.choices}
    status=request.GET.get('status','')
    if status: visible=[obj for obj in visible if obj.status==status]
    page,meta=page_data(visible,request)
    return control.JsonResponse({**meta,'counts':counts,'statuses':list(Order.Status.choices),'rows':[
        {'id':str(obj.pk),'reference':obj.reference,'source':obj.source,**payments.summary(obj),'delivery_zone':obj.delivery_zone,'revision':obj.revision,'can_mark_payment':allowed(ma,request,obj,True) and request.user.has_perm('sanjilas.mark_payment'),
        'customer':obj.customer_name,'status':obj.status,**payments.summary(obj),
         'total':obj.total,'currency':obj.currency,'created_at':obj.created_at.isoformat()} for obj in page]})


@control.operator_required
@require_GET
@transaction.atomic
def order_detail(request,pk):
    from .invoice_edits import can_edit
    from .models import InvoiceRevision
    ma=admin.site._registry[Order]
    obj=get_object_or_404(ma.get_queryset(request).select_for_update(),pk=pk)
    if not allowed(ma,request,obj): raise PermissionDenied
    form=ma.get_form(request,obj)(instance=obj)
    can_change=allowed(ma,request,obj,True) and 'status' in form.fields and not form.fields['status'].disabled and 'status' not in ma.get_readonly_fields(request,obj)
    transitions={'placed':['processing','cancelled'],'processing':['shipped','cancelled'],'shipped':['completed'],'completed':[],'cancelled':[]}
    item_admin=admin.site._registry[Order._meta.get_field('items').related_model]
    items=item_admin.get_queryset(request).filter(order=obj) if allowed(item_admin,request) else []
    return control.JsonResponse({'id':str(obj.pk),'reference':obj.reference,'status':obj.status,'can_edit_invoice':can_edit(request,obj),'can_history':allowed(admin.site._registry[InvoiceRevision],request),
        **payments.summary(obj),
        'payments':payments.entries(obj,request),'advance_pending':obj.payment_method=='delivery_advance' and not obj.advance_verified,'advance_reference':obj.advance_reference,'advance_amount':obj.advance_amount,'advance_channel':obj.advance_channel,
        'regular_subtotal':sum(item.regular_price*item.quantity for item in obj.items.all()),
        'discount_total':sum((item.regular_price-item.unit_price)*item.quantity for item in obj.items.all()),
        **payments.summary(obj),'delivery_zone':obj.delivery_zone,'revision':obj.revision,'can_mark_payment':allowed(ma,request,obj,True) and request.user.has_perm('sanjilas.mark_payment'),
        'customer':obj.customer_name,'email':obj.email,'phone':obj.phone,'address':obj.address,'area':obj.area,'city':obj.city,
        'postal_code':obj.postal_code,'notes':obj.notes,'created_at':obj.created_at.isoformat(),
        'subtotal':obj.subtotal,'shipping_fee':obj.shipping_fee,'total':obj.total,'currency':obj.currency,
        'statuses':list(Order.Status.choices),'actions':transitions[obj.status] if can_change else [],
        'items':[{'name':item.product_name,'variant':item.variant_name,'sku':item.sku,'quantity':item.quantity,'regular_price':item.regular_price,'discount':(item.regular_price-item.unit_price)*item.quantity,'unit_price':item.unit_price,'total':item.line_total} for item in items if allowed(item_admin,request,item)]})


def stock_queryset(model,request):
    ma=admin.site._registry[model]
    if not allowed(ma,request): return []
    holds=CartItem.objects.filter(expires_at__gt=timezone.now())
    if model is Product:
        qs=ma.get_queryset(request).filter(variants__isnull=True)
        holds=holds.filter(product_id=OuterRef('pk'),variant__isnull=True)
        group='product_id'
    else:
        qs=ma.get_queryset(request).select_related('product')
        holds=holds.filter(variant_id=OuterRef('pk'))
        group='variant_id'
    held=holds.order_by().values(group).annotate(total=Sum('quantity')).values('total')
    return qs.annotate(reserved=Coalesce(Subquery(held,output_field=IntegerField()),0))


def stock_row(obj,request):
    ma=admin.site._registry[type(obj)]
    variant=isinstance(obj,ProductVariant)
    return {'id':obj.pk,'model':obj._meta.model_name,'name':obj.product.name if variant else obj.name,
        'variant':obj.name if variant else '', 'sku':obj.sku or '', 'on_hand':obj.stock_quantity,
        'reserved':obj.reserved,'available':max(0,obj.stock_quantity-obj.reserved),'tracked':obj.track_stock,
        'can_history':allowed(admin.site._registry[InventoryMovement],request),
        'can_change':allowed(ma,request,obj,True) and 'stock_quantity' not in ma.get_readonly_fields(request,obj),
        'product_id':obj.product_id if variant else obj.pk}


@control.operator_required
@require_GET
def stock(request):
    if not any(allowed(admin.site._registry[model],request) for model in [Product,ProductVariant]): raise PermissionDenied
    rows=[]
    term=request.GET.get('q','').strip().casefold()[:120]
    threshold=SiteSettings.load().low_stock_threshold
    for model in [Product,ProductVariant]:
        ma=admin.site._registry[model]
        for obj in stock_queryset(model,request):
            if not allowed(ma,request,obj): continue
            row=stock_row(obj,request)
            if term and term not in f"{row['name']} {row['variant']} {row['sku']}".casefold(): continue
            rows.append(row)
    summary={'on_hand':sum(row['on_hand'] for row in rows),'reserved':sum(row['reserved'] for row in rows),
             'available':sum(row['available'] for row in rows),'low':sum(row['tracked'] and row['available']<=threshold for row in rows)}
    state=request.GET.get('state','')
    if state=='low': rows=[row for row in rows if row['tracked'] and row['available']<=threshold]
    if state=='untracked': rows=[row for row in rows if not row['tracked']]
    page,meta=page_data(rows,request)
    return control.JsonResponse({**meta,'rows':list(page),'summary':summary,'threshold':threshold})


def get_stock(request,model,pk,write=False):
    if model not in ['product','productvariant']: raise control.Http404
    ma=control.resolve_admin('sanjilas',model)
    obj=get_object_or_404(ma.get_queryset(request),pk=pk)
    if not allowed(ma,request,obj,write): raise PermissionDenied
    return ma,obj


@control.operator_required
@require_GET
def movements(request,model,pk):
    _,obj=get_stock(request,model,pk)
    ma=admin.site._registry[InventoryMovement]
    if not allowed(ma,request): raise PermissionDenied
    filters={'variant_id':obj.pk} if isinstance(obj,ProductVariant) else {'product_id':obj.pk,'variant__isnull':True}
    rows=ma.get_queryset(request).filter(**filters).select_related('actor','order')
    return control.JsonResponse({'rows':[{'quantity':row.quantity,'reason':row.get_reason_display(),'note':row.note,
        'actor':row.actor.get_username() if row.actor_id else '', 'reference':row.order.reference if row.order_id else '',
        'created_at':row.created_at.isoformat()} for row in rows[:30] if allowed(ma,request,row)]})


@control.operator_required
@require_POST
@transaction.atomic
def adjust(request,model,pk):
    ma,obj=get_stock(request,model,pk,True)
    if isinstance(obj,ProductVariant): Product.objects.select_for_update().get(pk=obj.product_id)
    obj=get_object_or_404(ma.get_queryset(request).select_for_update(),pk=pk)
    if not allowed(ma,request,obj,True): raise PermissionDenied
    try:
        delta=int(request.POST.get('delta',''))
        expected=int(request.POST.get('expected',''))
    except (ValueError,TypeError): raise ValidationError({'stock_quantity':'Enter whole numbers.'})
    note=request.POST.get('note','').strip()
    if not note or len(note)>500 or delta==0: raise ValidationError({'note':control.labels()['ops_reason_required']})
    if obj.stock_quantity!=expected: return control.api_error('ops_stock_changed',409)
    form_class=ma.get_form(request,obj,change=True,fields=['stock_quantity'])
    if 'stock_quantity' in ma.get_readonly_fields(request,obj) or 'stock_quantity' not in form_class.base_fields or form_class.base_fields['stock_quantity'].disabled:
        raise PermissionDenied
    form=form_class({'stock_quantity':obj.stock_quantity+delta},instance=obj)
    if not form.is_valid(): return control.api_error('invalid_form',errors={key:list(value) for key,value in form.errors.items()})
    saved=ma.save_form(request,form,change=True)
    saved._stock_actor=request.user;saved._stock_note=note
    ma.save_model(request,saved,form,change=True)
    ma.save_related(request,form,[],change=True)
    ma.log_change(request,saved,ma.construct_change_message(request,form,[],add=False))
    return control.JsonResponse({'message':control.labels()['saved']})


# Legacy boolean endpoint intentionally rejects writes; use the payment ledger.
@control.operator_required
@require_POST
def payment(request,pk):
    raise ValidationError(control.labels()['payment_use_ledger'])

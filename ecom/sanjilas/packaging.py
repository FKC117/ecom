"""Packaging department queue and explicit physical handover."""
from decimal import Decimal
from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from . import control, payments
from .branding import public_settings
from .models import Order, OrderItem, PackagingTask, Shipment, SiteSettings
from .operations import allowed, page_data
from .shipments import scoped


class PackForm(forms.Form):
    expected_version = forms.IntegerField(min_value=1)
    item_weight = forms.DecimalField(min_value=Decimal('0.5'), max_value=10, decimal_places=2, label='Packed parcel weight (kg)')
    item_quantity = forms.IntegerField(min_value=1, max_value=100, label='Number of parcels')


def task_for_order(request, order, write=False):
    ma = admin.site._registry[PackagingTask]
    task = get_object_or_404(ma.get_queryset(request), order=order)
    return scoped(request, PackagingTask, task.pk, write=write)


def accessible(request, task):
    ma = admin.site._registry[Order]
    return allowed(ma, request, task.order) and ma.get_queryset(request).filter(pk=task.order_id).exists()


@control.operator_required
@require_GET
def queue(request):
    ma = admin.site._registry[PackagingTask]
    if not allowed(ma, request):
        raise PermissionDenied
    qs = ma.get_queryset(request).select_related('order', 'packed_by').filter(order__status='processing').exclude(state='cancelled')
    rows = [task for task in qs if allowed(ma, request, task) and accessible(request, task)]
    page, meta = page_data(rows, request)
    return JsonResponse({**meta, 'rows': [{'id':t.pk, 'order_id':str(t.order_id), 'reference':t.order.reference,
        'customer':t.order.customer_name, 'state':t.get_state_display(), 'queued_at':t.queued_at.isoformat(),
        'packed_by':t.packed_by.get_username() if t.packed_by else ''} for t in page]})


@control.operator_required
@require_GET
def detail(request, pk):
    order = scoped(request, Order, pk)
    task = task_for_order(request, order)
    ma = admin.site._registry[OrderItem]
    if not allowed(ma, request):
        raise PermissionDenied
    items = [item for item in ma.get_queryset(request).filter(order=order) if allowed(ma, request, item)]
    return JsonResponse({'task_id':task.pk, 'state':task.state, 'state_label':task.get_state_display(),
        'can_pack':order.status == 'processing' and not order.shipments.filter(environment='live').exclude(state='failed').exists(),
        'can_change':request.user.has_perm('sanjilas.change_packagingtask') and allowed(admin.site._registry[Order], request, order, True),
        'order':{'id':str(order.pk), 'reference':order.reference, 'revision':order.revision, 'status':order.status,
                 'customer':order.customer_name, 'address':order.address, 'area':order.area, 'zone':order.zone, 'city':order.city,
                 'phone':order.phone, 'notes':order.notes, **payments.summary(order)},
        'item_weight':task.item_weight, 'item_quantity':task.item_quantity,
        'items':[{'name':i.product_name, 'variant':i.variant_name, 'sku':i.sku, 'quantity':i.quantity} for i in items]})


def locked_task(request, pk):
    order = scoped(request, Order, pk, write=True, lock=True)
    task = task_for_order(request, order, write=True)
    if order.status != 'processing' or order.review_status in ('pending', 'rejected'):
        raise ValidationError('Only approved processing orders can be packed or handed over.')
    return order, task


@control.operator_required
@require_POST
@transaction.atomic
def pack(request, pk):
    order, task = locked_task(request, pk)
    form = PackForm(request.POST)
    if not form.is_valid():
        raise ValidationError({k:list(v) for k,v in form.errors.items()})
    data = form.cleaned_data
    if data['expected_version'] != order.revision:
        raise ValidationError(control.labels()['invoice_stale'])
    if order.shipments.filter(environment='live').exclude(state='failed').exists() or task.state == 'handed_over':
        raise ValidationError('Parcel details are locked after courier booking.')
    task.state = 'packed'
    task.item_weight = data['item_weight']
    task.item_quantity = data['item_quantity']
    task.packed_revision = order.revision
    task.packed_by = request.user
    task.packed_at = timezone.now()
    task.save()
    admin.site._registry[PackagingTask].log_change(request, task, 'Parcel packing details saved.')
    return JsonResponse({'ok':True})


@control.operator_required
@require_POST
@transaction.atomic
def handover(request, pk):
    order, task = locked_task(request, pk)
    shipment = scoped(request, Shipment, forms.IntegerField(min_value=1).clean(request.POST.get('shipment')))
    if shipment.order_id != order.pk or shipment.state != 'booked' or not shipment.consignment_id:
        raise ValidationError('A successful courier booking is required before handover.')
    if shipment.environment != 'live':
        raise ValidationError('Sandbox labels are tests; a live booking is required for physical handover.')
    if task.state != 'packed' or task.packed_revision != order.revision:
        raise ValidationError('Pack and verify the current invoice before handover.')
    # Enforce the same order form/read-only hooks as the standard order control.
    ma = admin.site._registry[Order]
    form = ma.get_form(request, order)(data={'status':'shipped'}, instance=order)
    if 'status' not in form.fields or form.fields['status'].disabled or 'status' in ma.get_readonly_fields(request, order):
        raise PermissionDenied
    if not form.is_valid():
        raise ValidationError({k:list(v) for k,v in form.errors.items()})
    ma.save_model(request, form.save(commit=False), form, True)
    ma.log_change(request, order, 'Packaging team confirmed physical courier handover.')
    task.state = 'handed_over'
    task.handed_by = request.user
    task.handed_at = timezone.now()
    task.save()
    admin.site._registry[PackagingTask].log_change(request, task, 'Handed to courier.')
    return JsonResponse({'ok':True})


@control.operator_required
@require_GET
def label(request, shipment_id):
    shipment = scoped(request, Shipment, shipment_id)
    order = scoped(request, Order, shipment.order_id)
    task_for_order(request, order)
    if shipment.state != 'booked' or not shipment.consignment_id:
        raise ValidationError('Book the courier before printing the parcel label.')
    return JsonResponse({'site':public_settings(SiteSettings.load(), request), 'labels':control.labels(),
        'shipment':{'account':str(shipment.account), 'environment':shipment.environment, 'consignment_id':shipment.consignment_id,
                    'reference':order.reference, **shipment.request_payload}})

"""Append-only staff payment ledger; all writers serialize on the parent order."""
import uuid
from decimal import Decimal
from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from . import control
from .models import Order,OrderPayment,InvoiceRevision


def summary(order):
    rows=list(order.payments.all())
    received=sum((r.amount for r in rows if r.kind=='payment'),Decimal('0.00'))
    refunded=sum((r.amount for r in rows if r.kind=='refund'),Decimal('0.00'))
    net=received-refunded
    payable=Decimal('0.00') if order.status=='cancelled' else order.total
    return {'simulated':any(r.is_simulated for r in rows),'received':received,'refunded':refunded,'net_paid':net,'amount_due':max(Decimal('0.00'),payable-net),
            'refund_due':max(Decimal('0.00'),net-payable),
            'payment_status':'paid' if net>=payable else 'partial' if net>0 else 'unpaid'}


def entries(order,request=None):
    rows=order.payments.select_related('actor')
    if request is not None:
        from .operations import allowed
        ma=admin.site._registry[OrderPayment]
        if not allowed(ma,request):return []
        rows=[row for row in ma.get_queryset(request).filter(order=order).select_related('actor') if allowed(ma,request,row)]
    return [{'id':r.pk,'is_simulated':r.is_simulated,'kind':r.kind,'amount':r.amount,'method':r.method,'reference':r.reference,
             'occurred_at':r.occurred_at.isoformat(),'actor':r.actor.get_username() if r.actor_id else '',
             'notes':r.notes} for r in rows]


class PaymentForm(forms.ModelForm):
    class Meta:
        model=OrderPayment
        fields=['kind','amount','method','reference','occurred_at','notes']


@control.operator_required
@require_POST
@transaction.atomic
def record(request,pk):
    from .operations import allowed
    ma=admin.site._registry[Order]
    order=get_object_or_404(ma.get_queryset(request).select_for_update(),pk=pk)
    if not allowed(ma,request,order,True) or not request.user.has_perm('sanjilas.mark_payment'):raise PermissionDenied
    try:key=uuid.UUID(request.POST.get('operation_key',''))
    except (ValueError,TypeError):raise ValidationError(control.labels()['invalid_form'])
    previous=OrderPayment.objects.filter(operation_key=key).first()
    if previous:
        if previous.order_id!=order.pk or previous.actor_id!=request.user.pk:raise PermissionDenied
        return control.JsonResponse(summary(order))
    if request.POST.get('expected_version')!=str(order.revision):raise ValidationError(control.labels()['invoice_stale'])
    form=PaymentForm(request.POST)
    if not form.is_valid():raise ValidationError({k:list(v) for k,v in form.errors.items()})
    return control.JsonResponse(append(request,order,form.save(commit=False),key))


def append(request,order,row,key):
    from .invoice_edits import snapshot
    ma=admin.site._registry[Order]
    balances=summary(order)
    if row.occurred_at>timezone.now():raise ValidationError(control.labels()['payment_future'])
    if row.kind=='payment' and row.amount>balances['amount_due']:raise ValidationError(control.labels()['payment_excess'])
    if row.kind=='refund' and row.amount>balances['net_paid']:raise ValidationError(control.labels()['refund_excess'])
    before=snapshot(order)
    if row.method=='dummy':row.is_simulated=True
    row.order=order;row.actor=request.user;row.operation_key=key;row._payment_write=True;row.save()
    if order.payment_method=='delivery_advance' and row.kind=='payment' and row.reference==order.advance_reference and row.method==order.advance_channel and row.amount==order.advance_amount:order.advance_verified=True
    order.payment_status=summary(order)['payment_status'];order.revision+=1;order._commerce_write=True;order.save()
    InvoiceRevision.objects.create(order=order,version=order.revision,actor=request.user,reason=row.notes,before=before,after=snapshot(order))
    admin.site._registry[OrderPayment].log_addition(request,row,row.notes)
    ma.log_change(request,order,row.notes)
    return summary(order)

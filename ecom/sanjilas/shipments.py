"""Staff shipment workflow. Reserve locally before making an external booking."""
import uuid
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from . import control
from .couriers import CourierError, adapter
from .models import CourierAccount, Order, Shipment
from .operations import allowed


class BookingForm(forms.Form):
    account = forms.IntegerField(min_value=1, label='Courier account')
    expected_version = forms.IntegerField(min_value=1)
    item_weight = forms.DecimalField(min_value=Decimal('0.5'), max_value=10, decimal_places=2, label='Parcel weight (kg)')
    item_quantity = forms.IntegerField(min_value=1, max_value=100, initial=1, label='Number of parcels')
    delivery_type = forms.TypedChoiceField(label='Delivery service', choices=[(48, 'Normal delivery'), (12, 'On demand delivery')], coerce=int)
    recipient_city = forms.IntegerField(required=False, min_value=1, label='City')
    recipient_zone = forms.IntegerField(required=False, min_value=1, label='Zone')
    recipient_area = forms.IntegerField(required=False, min_value=1, label='Area (optional)')
    special_instruction = forms.CharField(required=False, max_length=500, label='Courier instructions')

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('recipient_zone') and not cleaned.get('recipient_city'):
            self.add_error('recipient_city', 'Select a Pathao city when providing a zone.')
        if cleaned.get('recipient_area') and not cleaned.get('recipient_zone'):
            self.add_error('recipient_zone', 'Select a Pathao zone when providing an area.')
        return cleaned


def scoped(request, model, pk, write=False, lock=False):
    ma = admin.site._registry[model]
    qs = ma.get_queryset(request)
    obj = get_object_or_404(qs.select_for_update() if lock else qs, pk=pk)
    if not allowed(ma, request, obj, write):
        raise PermissionDenied
    return obj


def can_book(request, order):
    ma = admin.site._registry[Shipment]
    return (allowed(admin.site._registry[Order], request, order, True)
            and ma.has_module_permission(request) and request.user.has_perm('sanjilas.add_shipment'))


def visible_accounts(request):
    ma = admin.site._registry[CourierAccount]
    if not allowed(ma, request):
        return []
    return [row for row in ma.get_queryset(request).filter(is_active=True) if allowed(ma, request, row)]


def serialize(row):
    return {'id': row.pk, 'account': str(row.account), 'environment': row.environment,
            'state': row.state, 'state_label': row.get_state_display(), 'consignment_id': row.consignment_id, 'merchant_order_id': row.merchant_order_id,
            'courier_status': row.courier_status, 'delivery_fee': row.delivery_fee,
            'last_error': row.last_error, 'amount_to_collect': row.request_payload.get('amount_to_collect'),
            'can_reconcile': row.state in ('submitting', 'uncertain'), 'updated_at': row.updated_at.isoformat()}


@control.operator_required
@require_GET
def detail(request, pk):
    order = scoped(request, Order, pk)
    ma = admin.site._registry[Shipment]
    rows = []
    if allowed(ma, request):
        rows = [serialize(row) for row in ma.get_queryset(request).filter(order=order).select_related('account') if allowed(ma, request, row)]
    fields = [{'name': name, 'label': field.label, 'required': field.required,
               'choices': list(getattr(field, 'choices', [])),
               'type': 'number' if isinstance(field, (forms.IntegerField, forms.DecimalField)) else 'text',
               'min': getattr(field, 'min_value', None), 'max': getattr(field, 'max_value', None),
               'step': '0.01' if isinstance(field, forms.DecimalField) else '1',
               'max_length': getattr(field, 'max_length', None)}
              for name, field in BookingForm.base_fields.items() if name not in ('account', 'expected_version')]
    return JsonResponse({'rows': rows, 'fields': fields, 'can_book': can_book(request, order),
                         'can_refresh': request.user.has_perm('sanjilas.change_shipment'),
                         'accounts': [{'id': row.pk, 'name': str(row), 'environment': row.environment} for row in visible_accounts(request)]})


@control.operator_required
@require_POST
@transaction.non_atomic_requests
def book(request, pk):
    form = BookingForm(request.POST)
    if not form.is_valid():
        raise ValidationError({key: list(errors) for key, errors in form.errors.items()})
    data = form.cleaned_data
    with transaction.atomic():
        order = scoped(request, Order, pk, write=True, lock=True)
        if not can_book(request, order):
            raise PermissionDenied
        if not admin.site._registry[Shipment].has_add_permission(request):
            raise PermissionDenied
        account = scoped(request, CourierAccount, data['account'])
        if not account.is_active:
            raise ValidationError('This courier account is inactive.')
        if order.revision != data['expected_version']:
            raise ValidationError(control.labels()['invoice_stale'])
        client = adapter(account)
        row = Shipment.objects.filter(order=order, environment=account.environment).first()
        if row and row.state != 'failed':
            raise ValidationError('This order already has a shipment in this environment. Refresh or reconcile it before retrying.')
        merchant_id = row.merchant_order_id if row else f'{account.environment}-{uuid.uuid4().hex}'
        payload = client.payload(order, account, data, merchant_id)
        from .models import PackagingTask
        task = PackagingTask.objects.filter(order=order).first()
        if task and (task.state != 'packed' or task.packed_revision != order.revision):
            raise ValidationError('The packaging team must pack and verify the current invoice before booking.')
        if task and (task.item_weight != data['item_weight'] or task.item_quantity != data['item_quantity']):
            raise ValidationError('Courier parcel details must match the packed weight and parcel count.')
        validate_locations(account, data, request)
        # Tokens are obtained before reserving a booking; auth failures cannot have created an order.
        try:
            client.token()
        except CourierError as error:
            raise ValidationError(str(error)) from None
        if row:
            row.account = account
            row.state = 'submitting'
            row.request_payload = payload
            row.last_error = ''
            row.actor = request.user
            row.save()
        else:
            row = Shipment.objects.create(order=order, account=account, environment=account.environment,
                                          merchant_order_id=merchant_id, state='submitting', request_payload=payload, actor=request.user)
        admin.site._registry[Shipment].log_addition(request, row, 'Courier booking started.')
    # The reservation is committed even if the provider times out or this worker stops.
    try:
        result = client.book(payload).get('data')
        if not isinstance(result, dict) or not isinstance(result.get('consignment_id'), str) or not result['consignment_id'] or len(result['consignment_id']) > 100:
            raise CourierError('Pathao did not return a valid consignment ID. Reconcile before retrying.')
        fee = Decimal(str(result.get('delivery_fee', 0)))
        if not fee.is_finite() or fee < 0 or fee >= Decimal('10000000000'):
            raise CourierError('Pathao returned an invalid delivery fee. Reconcile before retrying.')
        row.consignment_id = result['consignment_id']
        row.courier_status = str(result.get('order_status', ''))[:100]
        row.delivery_fee = fee
        row.state = 'booked'
    except (CourierError, InvalidOperation, TypeError, ValueError) as error:
        row.state = 'failed' if isinstance(error, CourierError) and error.rejected else 'uncertain'
        row.last_error = str(error) if isinstance(error, CourierError) else 'Invalid booking response. Reconcile before retrying.'
    with transaction.atomic():
        current = Shipment.objects.select_for_update().get(pk=row.pk)
        if current.state == 'booked':
            row = current
        else:
            row.save()
            admin.site._registry[Shipment].log_change(request, row, f'Courier booking: {row.state}.')
    return JsonResponse({**serialize(row), **({'error': row.last_error} if row.state != 'booked' else {})}, status=200 if row.state == 'booked' else 409)


@control.operator_required
@require_POST
def refresh(request, pk, shipment_id):
    # Same order lock as bookings/payments; reconcile only with a verified merchant reference.
    with transaction.atomic():
        order = scoped(request, Order, pk, write=True, lock=True)
        row = scoped(request, Shipment, shipment_id)
        if row.order_id != order.pk or not admin.site._registry[Shipment].has_change_permission(request, row):
            raise PermissionDenied
        account = scoped(request, CourierAccount, row.account_id)
        consignment = row.consignment_id or request.POST.get('consignment_id', '').strip()
        if not consignment or len(consignment) > 100:
            raise ValidationError('Enter the consignment ID from the courier merchant portal to reconcile this booking.')
        try:
            result = adapter(account).info(consignment).get('data')
        except CourierError as error:
            raise ValidationError(str(error)) from None
        if not isinstance(result, dict) or result.get('consignment_id') != consignment or result.get('merchant_order_id') != row.merchant_order_id:
            raise ValidationError('The consignment does not match this shipment merchant reference.')
        row.consignment_id = consignment
        from .courier_webhooks import apply_verified_status
        apply_verified_status(row, result)
        admin.site._registry[Shipment].log_change(request, row, 'Courier status refreshed / reconciled.')
    return JsonResponse(serialize(row))


@control.operator_required
@require_GET
def locations(request, account_id, kind):
    account = scoped(request, CourierAccount, account_id)
    parent = forms.IntegerField(min_value=1).clean(request.GET.get('parent')) if kind in ('zones','areas') else None
    from .courier_directory import database_choices
    return JsonResponse({'choices':database_choices(account, kind, parent, request)})


def fetch_location_choices(client, kind, parent=None):
    if kind not in ('cities','zones','areas','stores'):
        raise ValidationError('Unknown courier location list.')
    try:
        result = getattr(client, kind)(parent) if kind in ('zones','areas') else getattr(client, kind)()
        rows = result['data']['data']
        if not isinstance(rows, list): raise ValueError
        prefix = {'cities':'city','zones':'zone','areas':'area','stores':'store'}[kind]
        choices = []
        for row in rows:
            value = int(row[f'{prefix}_id'])
            name = row[f'{prefix}_name']
            if value < 1 or not isinstance(name, str) or not name.strip(): raise ValueError
            available = row.get('home_delivery_available', True) if kind == 'areas' else row.get('is_active', True)
            choices.append({'id':value, 'name':name.strip(), 'available':available not in (False, 0, '0')})
    except CourierError:
        raise
    except (KeyError, TypeError, ValueError):
        raise ValidationError('Courier locations could not be loaded. Please retry.') from None
    return choices


def validate_locations(account, data, request=None):
    from .courier_directory import database_choices
    for field, kind, parent in [('recipient_city','cities',None), ('recipient_zone','zones',data.get('recipient_city')), ('recipient_area','areas',data.get('recipient_zone'))]:
        selected = data.get(field)
        if selected and not any(row['id'] == selected and row['available'] for row in database_choices(account, kind, parent, request)):
            raise ValidationError({field:'Select an available location belonging to the selected city or zone.'})


def guard_live_changes(order, allow_completed=False):
    if allow_completed and order.status == 'completed':
        return
    if order.shipments.filter(environment='live', state__in=['submitting', 'uncertain', 'booked']).exists():
        raise ValidationError('A live courier shipment exists. Reconcile delivery and collection with the courier before changing this invoice or cancelling it.')

"""Persistent courier geography. Only explicit staff refreshes contact the provider."""
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from . import control
from .models import CourierAccount, CourierLocation
from .operations import allowed
from .shipments import scoped


def database_choices(account, kind, parent=None, request=None):
    if kind not in ('cities','zones','areas'):
        raise ValidationError('Select cities, zones or areas from the saved courier directory.')
    qs = CourierLocation.objects.all()
    if request is not None:
        ma = admin.site._registry[CourierLocation]
        if not allowed(ma, request): raise PermissionDenied
        qs = ma.get_queryset(request)
    qs = qs.filter(account=account, is_active=True)
    if kind == 'cities':
        synced = account.cities_refreshed_at
        rows = qs.filter(kind=kind, parent__isnull=True)
    else:
        parent_kind = 'cities' if kind == 'zones' else 'zones'
        node = qs.filter(kind=parent_kind, external_id=parent).first()
        if node is None: raise ValidationError('Select a saved courier parent location.')
        synced = node.children_refreshed_at
        rows = qs.filter(kind=kind, parent=node)
    if not synced:
        raise ValidationError('These courier locations have not been imported. Ask an administrator to update the Courier locations directory.')
    if request is not None:
        rows = [row for row in rows if allowed(ma, request, row)]
    return [{'id':row.external_id,'name':row.name,'available':row.available} for row in rows]


def can_refresh(request, account):
    ma = admin.site._registry[CourierLocation]
    from .models import City,Zone,Area,CourierAddressMapping
    # Check before fetching the directory, so a staff account cannot spend the
    # entire API import only to discover it cannot publish the address mappings.
    for model in (City,Zone,Area,CourierAddressMapping):
        address_admin=admin.site._registry[model]
        if not address_admin.has_module_permission(request) or not address_admin.has_view_or_change_permission(request) or not address_admin.has_add_permission(request):
            return False
    return (allowed(admin.site._registry[CourierAccount],request,account,True)
            and ma.has_module_permission(request) and ma.has_change_permission(request))


@control.operator_required
@require_GET
def accounts(request):
    ma = admin.site._registry[CourierAccount]
    if not allowed(ma,request) or not allowed(admin.site._registry[CourierLocation],request): raise PermissionDenied
    rows = [row for row in ma.get_queryset(request) if allowed(ma,request,row)]
    from .courier_directory_sync import status
    return JsonResponse({'accounts':[{'id':row.pk,'name':str(row),'can_refresh':can_refresh(request,row),
        'sync':status(job) if (job:=row.directory_syncs.first()) else None,
        'cities_refreshed_at':row.cities_refreshed_at} for row in rows]})


@control.operator_required
@require_POST
def refresh(request,account_id):
    account = scoped(request,CourierAccount,account_id,write=True)
    from .courier_directory_sync import enqueue,status
    job=enqueue(request,account)
    return JsonResponse({'sync':status(job)},status=202)

"""Courier-independent addresses and explicit mappings to courier-owned IDs."""
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.cache import never_cache
from .models import City,Zone,Area,CourierAddressMapping,CourierLocation


def directory():
    return {'cities':list(City.objects.filter(is_active=True).values('id','name')),
            'zones':list(Zone.objects.filter(is_active=True,city__is_active=True).values('id','name','city_id')),
            'areas':list(Area.objects.filter(is_active=True,city__is_active=True).values('id','name','city_id','zone_id'))}


def _find(qs,value):
    return qs.filter(pk=int(value)).first() if str(value).isdigit() else qs.filter(name__iexact=str(value).strip()).first()


def resolve(city,area,required=True,zone=None):
    if not city and not area and not zone and not required:
        return {'city':'','zone':'','area':'','city_record':None,'zone_record':None,'area_record':None}
    city_obj=_find(City.objects.filter(is_active=True),city)
    if not city_obj:raise ValidationError({'city':'Choose a valid city.'})
    zones=Zone.objects.filter(city=city_obj,is_active=True)
    zone_obj=_find(zones,zone) if zone else None
    if (zone or zones.exists()) and not zone_obj:raise ValidationError({'zone':'Choose a zone belonging to the selected city.'})
    area_obj=_find(Area.objects.filter(city=city_obj,zone=zone_obj,is_active=True),area) if area else None
    if area and not area_obj:raise ValidationError({'area':'Choose an area belonging to the selected zone.'})
    return {'city':city_obj.name,'zone':zone_obj.name if zone_obj else '','area':area_obj.name if area_obj else '',
            'city_record':city_obj,'zone_record':zone_obj,'area_record':area_obj}


def _canonical_record(model,request,**values):
    if request is None:return model.objects.get_or_create(**values)[0]
    from django.contrib import admin
    from django.core.exceptions import PermissionDenied
    ma=admin.site._registry[model]
    obj=model.objects.filter(**values).first()
    if obj:
        if not ma.get_queryset(request).filter(pk=obj.pk).exists() or not ma.has_view_or_change_permission(request,obj):raise PermissionDenied
        return obj
    if not ma.has_module_permission(request) or not ma.has_add_permission(request):raise PermissionDenied
    data={key:getattr(value,'pk',value) for key,value in values.items()}
    if model in (City,Zone,Area):data['is_active']=True
    form=ma.get_form(request)(data=data)
    if not form.is_valid():raise ValidationError({key:list(value) for key,value in form.errors.items()})
    obj=ma.save_form(request,form,change=False)
    ma.save_model(request,obj,form,change=False)
    ma.save_related(request,form,[],change=False)
    ma.log_addition(request,obj,'Created address mapping from saved courier directory.')
    return obj


def map_published_directory(account,request=None):
    """Called by a manual directory import, never by checkout or an API lookup."""
    for kind in ('cities','zones','areas'):
        for location in CourierLocation.objects.filter(account=account,kind=kind,is_active=True).order_by('external_id'):
            if CourierAddressMapping.objects.filter(location=location).exists():continue
            if kind=='cities':
                obj=_canonical_record(City,request,name=location.name)
                values={'city':obj}
            else:
                parent=CourierAddressMapping.objects.filter(location_id=location.parent_id).first()
                if not parent:raise ValidationError('Import the parent address mapping first.')
                if kind=='zones':
                    obj=_canonical_record(Zone,request,city=parent.city,name=location.name)
                    values={'zone':obj}
                else:
                    obj=_canonical_record(Area,request,city=parent.zone.city,zone=parent.zone,name=location.name)
                    values={'area':obj}
            _canonical_record(CourierAddressMapping,request,location=location,**values)


def courier_destination(order,account):
    ids={'city':order.city_record_id,'zone':order.zone_record_id,'area':order.area_record_id}
    if not ids['city'] or not ids['zone']:return {}
    result={}
    parent=None
    for field,kind in [('city','cities'),('zone','zones'),('area','areas')]:
        if field=='area' and not ids['area']:continue
        mapping=CourierAddressMapping.objects.select_related('location').filter(location__account=account,location__kind=kind,
            location__is_active=True,location__available=True,**{field+'_id':ids[field]}).first()
        if not mapping or (parent is not None and mapping.location.parent_id!=parent):return {}
        result['recipient_'+field]=mapping.location.external_id
        parent=mapping.location_id
    return result


@never_cache
@require_GET
def search(request):
    kind=request.GET.get('kind','city');term=request.GET.get('q','').strip()[:150]
    if kind not in ['city','zone','area']:return JsonResponse({'results':[]},status=400)
    if kind=='city':rows=City.objects.filter(is_active=True)
    else:
        city=request.GET.get('city','')
        if not city.isdigit():return JsonResponse({'results':[]})
        if kind=='zone':rows=Zone.objects.filter(is_active=True,city__is_active=True,city_id=int(city))
        else:
            zone=request.GET.get('zone','')
            rows=Area.objects.filter(is_active=True,city__is_active=True,city_id=int(city))
            rows=rows.filter(zone_id=int(zone),zone__is_active=True) if zone.isdigit() else rows.filter(zone__isnull=True)
    if term:rows=rows.filter(name__icontains=term)
    try:page=max(1,min(100000,int(request.GET.get('page','1'))))
    except (TypeError,ValueError):return JsonResponse({'results':[]},status=400)
    results=list(rows.values('id','name')[(page-1)*20:page*20+1])
    return JsonResponse({'results':results[:20],'has_more':len(results)>20,'page':page})

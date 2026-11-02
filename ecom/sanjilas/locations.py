"""Canonical delivery locations; order text remains an invoice snapshot."""
from django.core.exceptions import ValidationError
from .models import City,Area

def directory():
    return {'cities':list(City.objects.filter(is_active=True).values('id','name')),
            'areas':list(Area.objects.filter(is_active=True,city__is_active=True).values('id','name','city_id'))}

def resolve(city,area,required=True):
    if not city and not area and not required:return {'city':'','area':'','city_record':None,'area_record':None}
    cities=City.objects.filter(is_active=True)
    city_obj=cities.filter(pk=int(city)).first() if str(city).isdigit() else cities.filter(name__iexact=str(city).strip()).first()
    if not city_obj:raise ValidationError({'city':'Choose a valid city.'})
    areas=Area.objects.filter(city=city_obj,is_active=True)
    area_obj=areas.filter(pk=int(area)).first() if str(area).isdigit() else areas.filter(name__iexact=str(area).strip()).first()
    if not area_obj:raise ValidationError({'area':'Choose an area belonging to the selected city.'})
    return {'city':city_obj.name,'area':area_obj.name,'city_record':city_obj,'area_record':area_obj}


from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.cache import never_cache

@never_cache
@require_GET
def search(request):
    kind=request.GET.get('kind','city')
    term=request.GET.get('q','').strip()[:150]
    if kind not in ['city','area']:return JsonResponse({'results':[]},status=400)
    if not term:return JsonResponse({'results':[]})
    if kind=='city':rows=City.objects.filter(is_active=True,name__icontains=term)
    else:
        city=request.GET.get('city','')
        if not city.isdigit():return JsonResponse({'results':[]})
        rows=Area.objects.filter(is_active=True,city__is_active=True,city_id=int(city),name__icontains=term)
    return JsonResponse({'results':list(rows.values('id','name')[:20])})

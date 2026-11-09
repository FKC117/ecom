"""Database-side listing prices, availability, filters and pagination."""
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urljoin
from django.db.models import Case, When, Value, F, Q, Sum, OuterRef, Subquery, Exists, DecimalField, IntegerField
from django.db.models.functions import Coalesce, Greatest, Round
from django.core.paginator import Paginator, InvalidPage
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import CartItem, ProductVariant

MONEY=DecimalField(max_digits=16,decimal_places=2)
SORTS={'featured':('position','pk'),'newest':('-pk',),'price_asc':(F('catalog_price').asc(nulls_last=True),'pk'),
       'price_desc':(F('catalog_price').desc(nulls_last=True),'pk'),'name':('name','pk')}


def annotated(query,site,cart=None,variant=False):
    holds=CartItem.objects.filter(expires_at__gt=timezone.now())
    if cart: holds=holds.exclude(cart=cart)
    holds=holds.filter(variant_id=OuterRef('pk')) if variant else holds.filter(product_id=OuterRef('pk'),variant__isnull=True)
    group='variant_id' if variant else 'product_id'
    holds=holds.order_by().values(group).annotate(total=Sum('quantity')).values('total')
    query=query.annotate(catalog_free=Greatest(Value(0),F('stock_quantity')-Coalesce(Subquery(holds,output_field=IntegerField()),0)))
    if variant:
        query=query.annotate(base_price=Coalesce('price','product__price'),
            mode=Case(When(override_discount=True,then=F('discount_type')),default=F('product__discount_type')),
            reduction=Case(When(override_discount=True,then=F('discount_value')),default=F('product__discount_value')))
    else: query=query.annotate(base_price=F('price'),mode=F('discount_type'),reduction=F('discount_value'))
    query=query.annotate(sale=Round(Case(When(mode='percent',then=F('base_price')*(Value(Decimal(100))-F('reduction'))/Value(Decimal(100))),
        When(mode='fixed',then=F('base_price')-F('reduction')),default=F('base_price'),output_field=MONEY),2))
    currency='product__currency' if variant else 'currency'
    query=query.annotate(buyable=Case(When(Q(track_stock=True,catalog_free__gt=0,sale__isnull=False)&Q(**{currency:site.shop_currency}),then=Value(1)),default=Value(0),output_field=IntegerField()))
    if variant: return query.annotate(rank=Case(When(buyable=1,then=0),When(track_stock=False,then=1),default=2,output_field=IntegerField()))
    active=annotated(ProductVariant.objects.filter(product_id=OuterRef('pk'),is_active=True),site,cart,True)
    lead=active.order_by('rank',F('sale').asc(nulls_last=True),'position','pk')
    return query.annotate(catalog_has_variants=Exists(ProductVariant.objects.filter(product_id=OuterRef('pk'))),
        catalog_price=Case(When(Exists(active),then=Subquery(lead.values('sale')[:1])),default=F('sale'),output_field=MONEY),
        catalog_buyable=Case(When(catalog_has_variants=True,then=Exists(active.filter(buyable=1))),default=Q(buyable=1)))


def paginate(query,params):
    filters={'q':params.get('q','').strip()[:150],'min_price':params.get('min_price','').strip(),
             'max_price':params.get('max_price','').strip(),'in_stock':params.get('in_stock')=='1','sort':params.get('sort','featured')}
    if filters['sort'] not in SORTS: raise ValidationError('catalog_invalid_sort')
    bounds={}
    for name in ['min_price','max_price']:
        if filters[name]:
            try:
                if len(filters[name])>20: raise InvalidOperation
                value=Decimal(filters[name])
                if not value.is_finite() or value<0 or value>Decimal('9999999999.99'): raise InvalidOperation
                bounds[name]=value
            except (InvalidOperation,ValueError): raise ValidationError('catalog_invalid_price')
    if len(bounds)==2 and bounds['min_price']>bounds['max_price']: raise ValidationError('catalog_invalid_range')
    if filters['q']: query=query.filter(Q(name__icontains=filters['q'])|Q(subtitle__icontains=filters['q'])|Q(sku__icontains=filters['q'])|Q(category__name__icontains=filters['q']))
    if 'min_price' in bounds: query=query.filter(catalog_price__gte=bounds['min_price'])
    if 'max_price' in bounds: query=query.filter(catalog_price__lte=bounds['max_price'])
    if filters['in_stock']: query=query.filter(catalog_buyable=True)
    raw_page=params.get('page','1')
    if not raw_page.isdecimal() or len(raw_page)>9 or int(raw_page)<1:return None,filters
    try: page=Paginator(query.order_by(*SORTS[filters['sort']]),24).page(raw_page)
    except InvalidPage: return None,filters
    return page,filters


def metadata(site,group,kind,request,number=1):
    title=group.name if group else site.get('catalog_title',site['site_name'])
    description=group.description if group else site['meta_description']
    path=f'/{kind}/{group.slug}/' if group else '/shop/'
    canonical=urljoin((site['site_url'] or request.build_absolute_uri('/')).rstrip('/')+'/',path.lstrip('/'))
    if number>1: canonical+='?'+urlencode({'page':number})
    image=urljoin(canonical,group.image.url) if group and group.image else site['og_image']
    result={**site,'site_url':canonical,'meta_title':f'{title} | {site["site_name"]}','meta_description':description or site['meta_description'],
        'og_title':f'{title} | {site["site_name"]}','og_description':description or site['meta_description'],'og_type':'website','og_image':image,
        'twitter_title':f'{title} | {site["site_name"]}','twitter_description':description or site['meta_description'],'twitter_image':image}
    if group and group.image: result.update(og_image_alt=group.image_alt or group.name,twitter_image_alt=group.image_alt or group.name)
    if any(request.GET.get(key) for key in ['q','min_price','max_price','in_stock','sort']): result['robots']='noindex, follow'
    return result

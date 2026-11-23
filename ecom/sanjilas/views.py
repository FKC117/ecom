from django.conf import settings as django_settings
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.db.models import ImageField, Prefetch
from django.utils.html import format_html, json_script
from .branding import public_settings
from .models import SiteSettings, HomePage, Category, Collection, Product, ProductVariant, ProductImage, ProductTag, Cart
from django.views.decorators.http import require_GET
from django.views.decorators.cache import never_cache
from django.core.paginator import Paginator
from .images import image_metadata
from .shop_copy import shop_labels
from .commerce import request_cart


@require_GET
def health(request):
    """Application liveness; database readiness is checked separately."""
    return JsonResponse({"status": "ok", "service": "sanjilas"})


@require_GET
def site_settings(request):
    return JsonResponse(public_settings(SiteSettings.load(), request))


@never_cache
@require_GET
def home_page(request, slug=None, listing_kind=None, listing_slug=None):
    page = HomePage.objects.filter(pk=1).first() or HomePage()

    def serialize(instance):
        data = {}
        for field in instance._meta.fields:
            value = getattr(instance, field.attname)
            if isinstance(field, ImageField):
                data[field.name + "_media"] = image_metadata(value)
                value = value.url if value else ""
            data[field.name] = value
        return data

    site = SiteSettings.load()
    from .commerce import reserved_quantity
    customer_cart = request_cart(request)

    def pricing(item):
        free = (item.catalog_free if hasattr(item,'catalog_free') else max(0,item.stock_quantity-reserved_quantity(item,exclude_cart=customer_cart))) if item.track_stock else 0
        return {'available_quantity': free, 'can_purchase': item.track_stock and free > 0 and item.discounted_price is not None and (item.product.currency if isinstance(item, ProductVariant) else item.currency) == site.shop_currency,
                ** {'regular_price': item.regular_price, 'discounted_price': item.discounted_price,
                'has_discount': item.regular_price is not None and item.discounted_price < item.regular_price,
                'availability': 'not_for_sale' if not item.track_stock else 'sold_out' if free == 0 and item.availability != 'backorder' else item.availability}}

    def tags(item):
        return [{'id': tag.pk, 'name': tag.name, 'slug': tag.slug} for tag in item.tags.all()]

    def catalog(product, compact=False):
        from .jewellery import details
        data = serialize(product)
        data['details'] = details(product,labels=page.labels) if not compact else []
        data.update(pricing(product))
        data['collections']=[item.pk for item in product.collections.all() if item.is_active]
        data['tags'] = tags(product) if not compact else []
        data['features'] = [{'id': f.pk, 'name': f.name, 'value': f.value} for f in product.features.all()] if not compact else []
        data['gallery'] = [serialize(image) for image in product.gallery.all()] if not compact else []
        data['variants'] = [{**pricing(variant),'currency':product.currency} if compact else {**serialize(variant), **pricing(variant), 'tags': tags(variant), 'currency': product.currency,
                            'details':details(product,variant,labels=page.labels), 'care_instructions':variant.care_instructions.strip() or product.care_instructions.strip()} for variant in product.variants.all()]
        has_variants = bool(data['variants']) or getattr(product, 'catalog_has_variants', False)
        preorder_options = data['variants'] if has_variants else [data]
        data['preorder_available'] = any(option['availability'] == 'backorder' for option in preorder_options)
        if data['variants']:
            variants = data['variants']
            available = [v for v in variants if v['can_purchase']] or [v for v in variants if v['availability'] != 'sold_out'] or variants
            priced = [v for v in available if v['discounted_price'] is not None]
            lead = min(priced, key=lambda v: v['discounted_price']) if priced else available[0]
            for key in ('regular_price', 'discounted_price', 'has_discount', 'availability', 'can_purchase', 'available_quantity'):
                data[key] = lead[key]
            data['has_price_range'] = len({v['discounted_price'] for v in variants}) > 1
        else:
            data['has_price_range'] = False
            if getattr(product,'catalog_has_variants',False) or product.variants.exists():
                data['can_purchase'] = False
        if compact:
            data={key:data[key] for key in ['id','name','slug','subtitle','price','currency','image','image_media','image_alt','badge','category','collections','is_featured','regular_price','discounted_price','has_discount','availability','can_purchase','available_quantity','has_price_range','preorder_available']}
        return data

    from .listings import annotated, paginate, metadata
    from django.core.exceptions import ValidationError
    group = None
    if listing_slug:
        group=(Category if listing_kind=='categories' else Collection).objects.filter(slug=listing_slug,is_active=True).first()
    catalog_query = annotated(Product.objects.filter(is_active=True, category__is_active=True),site,customer_cart).select_related('category').prefetch_related(
        'collections', Prefetch('tags', queryset=ProductTag.objects.filter(is_active=True)), 'features',
        Prefetch('gallery', queryset=ProductImage.objects.filter(is_active=True)),
        Prefetch('variants', queryset=annotated(ProductVariant.objects.filter(is_active=True),site,customer_cart,True).select_related('product').prefetch_related(Prefetch('tags', queryset=ProductTag.objects.filter(is_active=True)))),
    )
    product = catalog_query.filter(slug=slug).first() if slug else None
    products = catalog_query
    listing_data=None
    response_status=200
    listing_error=None
    if listing_kind:
        if listing_slug and not group:
            products=[];response_status=404
        else:
            if group: catalog_query=catalog_query.filter(**({'category':group} if listing_kind=='categories' else {'collections':group}))
            try: listing_page,filters=paginate(catalog_query,request.GET)
            except ValidationError as error:
                listing_error=page.labels.get(error.messages[0],error.messages[0]);listing_page=None;filters={};response_status=400
            if listing_page is None: products=[];response_status=404
            else:
                products=listing_page.object_list
                listing_data={'name':group.name if group else page.labels['catalog_title'],'description':group.description if group else '',
                    'page':listing_page.number,'pages':listing_page.paginator.num_pages,'count':listing_page.paginator.count,'filters':filters}
            if listing_error:
                response_status=400
                listing_data={'name':group.name if group else page.labels['catalog_title'],'description':group.description if group else '', 'page':1,'pages':1,'count':0,'filters':{}}
    if slug:
        products = list(catalog_query.filter(category=product.category).exclude(pk=product.pk)[:4]) if product else []
        if product and len(products)<4:
            products.extend(catalog_query.exclude(pk=product.pk).exclude(category=product.category)[:4-len(products)])
    if not slug and not listing_kind:
        if request.GET.get('directory')=='1':
            directory_page=Paginator(catalog_query,100).get_page(request.GET.get('page',1))
            products=directory_page.object_list
            listing_data={'page':directory_page.number,'pages':directory_page.paginator.num_pages,'count':directory_page.paginator.count}
        else: products=catalog_query.filter(is_featured=True)[:8]
    site_data = product_metadata(public_settings(site,request),product,request) if product else public_settings(site,request)
    if listing_kind:
        site_data=metadata({**site_data,'catalog_title':page.labels['catalog_title']},group,listing_kind,request,listing_data['page'] if listing_data else 1)
        if response_status>=400: site_data['robots']='noindex, nofollow'
    if slug and not product: site_data['robots']='noindex, nofollow'
    return JsonResponse({
        "site": site_data,
        "product": catalog(product) if product else None,
        "listing":listing_data,
        "error":listing_error,
        "page": {**serialize(page), 'labels': {**shop_labels(), **page.labels}},
        "categories": [serialize(item) for item in Category.objects.filter(is_active=True)],
        "collections": [serialize(item) for item in Collection.objects.filter(is_active=True)],
        "products": [catalog(item,compact=not slug) for item in products],
    }, status=404 if slug and not product else response_status)


def product_metadata(site, product, request):
    from django.utils.html import strip_tags
    from urllib.parse import urljoin
    origin = site['site_url'] or request.build_absolute_uri('/')
    url = urljoin(origin.rstrip('/')+'/', f'products/{product.slug}/')
    title = f"{product.name} | {site['site_name']}"
    description = strip_tags(product.description or product.subtitle)[:200] or site['meta_description']
    image = urljoin(origin, product.image.url) if product.image else site['og_image']
    return {**site, 'site_url':url, 'meta_title':title, 'meta_description':description,
            'og_title':title, 'og_description':description, 'og_type':'product', 'og_image':image,
            'og_image_alt':product.image_alt or product.name, 'twitter_title':title,
            'twitter_description':description, 'twitter_image':image, 'twitter_image_alt':product.image_alt or product.name}


@require_GET
def llms(request, full=False):
    settings = SiteSettings.load()
    return HttpResponse(settings.llms_full_txt if full else settings.llms_txt, content_type="text/plain; charset=utf-8")


@never_cache
@require_GET
def storefront(request, order_id=None, product_slug=None, listing_kind=None, listing_slug=None):
    """React document with metadata visible to crawlers without JavaScript."""
    if request.path=='/':
        from django.http import HttpResponsePermanentRedirect
        from django.urls import reverse
        for key,model,route in [('category',Category,'category'),('collection',Collection,'collection')]:
            value=request.GET.get(key,'')
            if value.isdecimal():
                group=model.objects.filter(pk=int(value),is_active=True).first() if len(value)<12 else None
                if group:return HttpResponsePermanentRedirect(reverse(route,kwargs={'listing_slug':group.slug}))
    index = django_settings.BASE_DIR.parent / "frontend" / "dist" / "index.html"
    if not index.exists():
        return HttpResponse("Build the React frontend first (npm run build).", status=503, content_type="text/plain")
    site = public_settings(SiteSettings.load(), request)
    page = HomePage.objects.filter(pk=1).first() or HomePage()
    product = Product.objects.filter(slug=product_slug,is_active=True,category__is_active=True).first() if product_slug else None
    group=None
    listing_status=200
    if listing_kind:
        from .listings import metadata, annotated, paginate
        from django.core.exceptions import ValidationError
        if listing_slug: group=(Category if listing_kind=='categories' else Collection).objects.filter(slug=listing_slug,is_active=True).first()
        listing_status=404 if listing_slug and not group else 200
        raw_page=request.GET.get('page','1')
        number=int(raw_page) if raw_page.isdecimal() and 0<int(raw_page)<1000000 else 1
        if listing_status==200:
            query=Product.objects.filter(is_active=True,category__is_active=True)
            if group:query=query.filter(**({'category':group} if listing_kind=='categories' else {'collections':group}))
            cart=request_cart(request)
            try:
                result,_=paginate(annotated(query,SiteSettings.load(),cart),request.GET)
                if result is None: listing_status=404
            except ValidationError: listing_status=400
        site=metadata({**site,'catalog_title':page.labels['catalog_title']},group,listing_kind,request,number)
        if listing_status>=400: site['robots']='noindex, nofollow'
    if request.path == '/sitemap/':
        from .seo import origin
        title = f"{page.labels.get('sitemap', 'Sitemap')} | {site['site_name']}"
        site = {**site, 'site_url': origin(request) + '/sitemap/', 'meta_title': title, 'og_title': title, 'twitter_title': title}
    if product: site = product_metadata(site,product,request)
    if product_slug and not product: site = {**site,'robots':'noindex, nofollow'}
    head = render_to_string("sanjilas/site_head.html", {"site": site})
    head += json_script({"labels": page.labels}, "storefront-bootstrap")
    document = index.read_text(encoding="utf-8").replace("<!--site-head-->", head)
    document = document.replace('<html lang="en">', format_html(
        '<html lang="en" data-palette="{}" data-mode="{}">', site["palette"], site["default_color_mode"]
    ))
    if request.path.startswith(("/control/", "/invoice/")):
        document = document.replace("</head>", '<meta name="robots" content="noindex, nofollow"></head>')
    return HttpResponse(document, status=404 if product_slug and not product else listing_status)

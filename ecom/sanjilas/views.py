from django.conf import settings as django_settings
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.db.models import ImageField, Prefetch
from django.utils.html import format_html, json_script
from .branding import public_settings
from .models import SiteSettings, HomePage, Category, Collection, Product, ProductVariant, ProductImage, ProductTag, Cart
from django.views.decorators.http import require_GET
from django.views.decorators.cache import never_cache
from .images import image_metadata
from .shop_copy import shop_labels


@require_GET
def health(request):
    """Application liveness; database readiness is checked separately."""
    return JsonResponse({"status": "ok", "service": "sanjilas"})


@require_GET
def site_settings(request):
    return JsonResponse(public_settings(SiteSettings.load(), request))


@never_cache
@require_GET
def home_page(request, slug=None):
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
    customer_cart = Cart.objects.filter(user=request.user).first() if request.user.is_authenticated else None

    def pricing(item):
        free = max(0, item.stock_quantity - reserved_quantity(item, exclude_cart=customer_cart)) if item.track_stock else 0
        return {'available_quantity': free, 'can_purchase': item.track_stock and free > 0 and item.discounted_price is not None and (item.product.currency if isinstance(item, ProductVariant) else item.currency) == site.shop_currency,
                ** {'regular_price': item.regular_price, 'discounted_price': item.discounted_price,
                'has_discount': item.regular_price is not None and item.discounted_price < item.regular_price,
                'availability': 'not_for_sale' if not item.track_stock else 'sold_out' if free == 0 else item.availability}}

    def tags(item):
        return [{'id': tag.pk, 'name': tag.name, 'slug': tag.slug} for tag in item.tags.all()]

    def catalog(product):
        from .jewellery import details
        data = serialize(product)
        data['details'] = details(product,labels=page.labels)
        data.update(pricing(product))
        data['collections']=[item.pk for item in product.collections.all() if item.is_active]
        data['tags'] = tags(product)
        data['features'] = [{'id': f.pk, 'name': f.name, 'value': f.value} for f in product.features.all()]
        data['gallery'] = [serialize(image) for image in product.gallery.all()]
        data['variants'] = [{**serialize(variant), **pricing(variant), 'tags': tags(variant), 'currency': product.currency,
                            'details':details(product,variant,labels=page.labels), 'care_instructions':variant.care_instructions.strip() or product.care_instructions.strip()} for variant in product.variants.all()]
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
            if product.variants.exists():
                data['can_purchase'] = False
        return data

    catalog_query = Product.objects.filter(is_active=True, category__is_active=True).prefetch_related(
        'collections', Prefetch('tags', queryset=ProductTag.objects.filter(is_active=True)), 'features',
        Prefetch('gallery', queryset=ProductImage.objects.filter(is_active=True)),
        Prefetch('variants', queryset=ProductVariant.objects.filter(is_active=True).select_related('product').prefetch_related(Prefetch('tags', queryset=ProductTag.objects.filter(is_active=True)))),
    )
    product = catalog_query.filter(slug=slug).first() if slug else None
    products = catalog_query
    if slug:
        products = list(catalog_query.filter(category=product.category).exclude(pk=product.pk)[:4]) if product else []
        if product and len(products)<4:
            products.extend(catalog_query.exclude(pk=product.pk).exclude(category=product.category)[:4-len(products)])
    site_data = product_metadata(public_settings(site,request),product,request) if product else public_settings(site,request)
    if slug and not product: site_data['robots']='noindex, nofollow'
    return JsonResponse({
        "site": site_data,
        "product": catalog(product) if product else None,
        "page": {**serialize(page), 'labels': {**shop_labels(), **page.labels}},
        "categories": [serialize(item) for item in Category.objects.filter(is_active=True)],
        "collections": [serialize(item) for item in Collection.objects.filter(is_active=True)],
        "products": [catalog(item) for item in products],
    }, status=404 if slug and not product else 200)


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
def storefront(request, order_id=None, product_slug=None):
    """React document with metadata visible to crawlers without JavaScript."""
    index = django_settings.BASE_DIR.parent / "frontend" / "dist" / "index.html"
    if not index.exists():
        return HttpResponse("Build the React frontend first (npm run build).", status=503, content_type="text/plain")
    site = public_settings(SiteSettings.load(), request)
    page = HomePage.objects.filter(pk=1).first() or HomePage()
    product = Product.objects.filter(slug=product_slug,is_active=True,category__is_active=True).first() if product_slug else None
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
    return HttpResponse(document, status=404 if product_slug and not product else 200)

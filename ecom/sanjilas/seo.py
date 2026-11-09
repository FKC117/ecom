"""Live discovery of canonical, public storefront documents."""
from urllib.parse import urlsplit
from xml.etree.ElementTree import Element, SubElement, tostring

from django.core.paginator import InvalidPage, Paginator
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_safe

from .models import Product, SiteSettings,Category,Collection

PAGE_SIZE = 5000
NAMESPACE = 'http://www.sitemaps.org/schemas/sitemap/0.9'


def origin(request):
    url = urlsplit(SiteSettings.load().site_url or request.build_absolute_uri('/'))
    return f'{url.scheme}://{url.netloc}'


def products():
    return Product.objects.filter(is_active=True, category__is_active=True).order_by('pk').only('slug')


def xml_response(root):
    return HttpResponse(tostring(root, encoding='utf-8', xml_declaration=True), content_type='application/xml; charset=utf-8')


@require_safe
def sitemap_index(request):
    paginator = Paginator(products(), PAGE_SIZE)
    base = origin(request)
    if paginator.num_pages == 1:
        return sitemap_urlset(base, paginator.page(1))

    root = Element('sitemapindex', xmlns=NAMESPACE)
    for number in paginator.page_range:
        entry = SubElement(root, 'sitemap')
        SubElement(entry, 'loc').text = base + reverse('sitemap-page', args=[number])
    return xml_response(root)


@require_safe
def sitemap_page(request, number):
    try:
        page = Paginator(products(), PAGE_SIZE).page(number)
    except InvalidPage as exc:
        raise Http404 from exc
    return sitemap_urlset(origin(request), page)


def sitemap_urlset(base, page):
    root = Element('urlset', xmlns=NAMESPACE)
    paths = []
    if page.number == 1:
        paths.extend([reverse('storefront'), reverse('sitemap-html')])
        paths.append(reverse('catalog'))
        paths.extend(reverse('category',kwargs={'listing_slug':obj.slug}) for obj in Category.objects.filter(is_active=True))
        paths.extend(reverse('collection',kwargs={'listing_slug':obj.slug}) for obj in Collection.objects.filter(is_active=True))
    paths.extend(reverse('product', kwargs={'product_slug': product.slug}) for product in page.object_list)
    for path in paths:
        entry = SubElement(root, 'url')
        SubElement(entry, 'loc').text = base + path
    return xml_response(root)


@require_safe
def robots(request):
    content = '\n'.join([
        'User-agent: *', 'Allow: /', 'Disallow: /admin/', 'Disallow: /control/',
        'Disallow: /api/', 'Disallow: /account/', 'Disallow: /login/',
        'Disallow: /invoice/', '', f'Sitemap: {origin(request)}{reverse("sitemap")}', '',
    ])
    return HttpResponse(content, content_type='text/plain; charset=utf-8')

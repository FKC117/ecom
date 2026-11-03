"""First-party browser tracking and explicitly trusted proxy IP resolution."""
import ipaddress,json,uuid,logging
from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError,transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from .models import Cart,Order,CommerceActivity

COOKIE='commerce_browser'
SALT='commerce-browser-v1'

def address(value):
    try:
        result=ipaddress.ip_address(value.strip())
        return result.ipv4_mapped if isinstance(result,ipaddress.IPv6Address) and result.ipv4_mapped else result
    except (ValueError,AttributeError):return None

def client_ip(request):
    peer=address(request.META.get('REMOTE_ADDR',''))
    if peer is None:return None
    trusted=[]
    for value in settings.COMMERCE_TRUSTED_PROXIES:
        try:trusted.append(ipaddress.ip_network(value,strict=False))
        except ValueError:continue
    def is_trusted(value):return any(value in network for network in trusted)
    if not is_trusted(peer):return str(peer)
    forwarded=request.META.get('HTTP_X_FORWARDED_FOR','')
    if not forwarded:return str(peer)
    chain=[address(value) for value in forwarded.split(',')]
    if len(chain)>20 or any(value is None for value in chain):return str(peer)
    current=peer
    for candidate in reversed(chain):
        if not is_trusted(current):break
        current=candidate
    return str(current)

class CommerceTrackingMiddleware:
    paths={'/api/shop/cart/':'cart_view','/api/shop/cart/items/':'cart_change','/api/shop/checkout/':'checkout'}
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        kind=self.paths.get(request.path)
        if not kind:return self.get_response(request)
        token=request.get_signed_cookie(COOKIE,default=None,salt=SALT,max_age=90*86400)
        try:token=str(uuid.UUID(token))
        except (ValueError,TypeError,AttributeError):token=str(uuid.uuid4())
        key=salted_hmac(SALT,token,algorithm='sha256').hexdigest()
        ip=client_ip(request);agent=request.META.get('HTTP_USER_AGENT','').replace('\x00','')[:512]
        request.commerce_context={'checkout_ip':ip,'browser_key':key,'user_agent':agent,'checkout_recorded_at':timezone.now()}
        response=self.get_response(request)
        response.set_signed_cookie(COOKIE,token,salt=SALT,max_age=90*86400,httponly=True,secure=request.is_secure() or settings.SESSION_COOKIE_SECURE,samesite='Lax')
        try:
            with transaction.atomic():self.record(request,response,kind,key,ip,agent)
        except DatabaseError:
            logging.getLogger(__name__).warning('Commerce activity could not be recorded.')
        return response

    def record(self,request,response,kind,key,ip,agent):
        user=request.user if request.user.is_authenticated and request.user.is_active else None
        cart=Cart.objects.filter(user=user).first() if user else None
        if cart:Cart.objects.filter(pk=cart.pk).update(last_ip=ip,browser_key=key,user_agent=agent,last_activity_at=timezone.now())
        order=None
        if kind=='checkout' and response.status_code==200 and user:
            try:order=Order.objects.filter(pk=json.loads(response.content)['order']['id'],user=user).first()
            except (ValueError,KeyError,TypeError):pass
        if kind!='cart_view' or cache.add('commerce-view:'+key,True,60):
            event=CommerceActivity(user=user,cart=cart,order=order,kind=kind,ip=ip,browser_key=key,user_agent=agent,response_status=response.status_code)
            event._tracking_write=True;event.save()


def order_context(request,order):
    from django.contrib import admin
    from .operations import allowed
    if not request.user.has_perm('sanjilas.view_order_tracking'):return None
    ma=admin.site._registry[CommerceActivity]
    rows=[]
    if allowed(ma,request):
        from django.db.models import Q
        query=Q(order=order)
        if order.browser_key and order.checkout_recorded_at:query|=Q(browser_key=order.browser_key,created_at__lte=order.checkout_recorded_at)
        rows=[{'kind':row.get_kind_display(),'ip':row.ip,'browser_key':row.browser_key,'status':row.response_status,'created_at':row.created_at.isoformat()} for row in ma.get_queryset(request).filter(query)[:20] if allowed(ma,request,row)]
    return {'ip':order.checkout_ip,'browser_key':order.browser_key,'user_agent':order.user_agent,'recorded_at':order.checkout_recorded_at.isoformat() if order.checkout_recorded_at else None,'events':rows}

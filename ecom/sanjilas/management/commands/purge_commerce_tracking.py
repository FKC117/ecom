from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from sanjilas.models import CommerceActivity,Order,Cart,CommerceLimit

class Command(BaseCommand):
    help='Remove commerce tracking metadata older than the configured retention period.'
    def handle(self,*args,**options):
        cutoff=timezone.now()-timedelta(days=max(1,settings.COMMERCE_TRACKING_RETENTION_DAYS))
        events,_=CommerceActivity.objects.filter(created_at__lt=cutoff).delete()
        CommerceLimit.objects.filter(expires_at__lte=timezone.now()).delete()
        orders=Order.objects.filter(checkout_recorded_at__lt=cutoff).update(checkout_ip=None,browser_key='',user_agent='',checkout_recorded_at=None)
        carts=Cart.objects.filter(last_activity_at__lt=cutoff).update(last_ip=None,browser_key='',user_agent='',last_activity_at=None)
        self.stdout.write(f'Removed tracking for {events} events, {orders} orders and {carts} carts.')

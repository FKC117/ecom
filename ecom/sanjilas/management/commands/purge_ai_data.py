from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from sanjilas.models import AIProductDraft, AIUsageCounter


class Command(BaseCommand):
    help = 'Clear expired AI draft content and remove usage counters older than seven days.'

    def handle(self, *args, **options):
        now = timezone.now()
        cleared = AIProductDraft.objects.filter(expires_at__lt=now).exclude(payload={}).update(payload={})
        removed, _ = AIUsageCounter.objects.filter(updated_at__lt=now - timedelta(days=7)).exclude(key='lock').delete()
        self.stdout.write(f'Cleared {cleared} expired draft payloads; removed {removed} old usage counters.')

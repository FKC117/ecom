import time
from django.core.management.base import BaseCommand
from sanjilas.courier_webhooks import process_one


class Command(BaseCommand):
    help = 'Verify pending courier callbacks against the provider API; use --watch for a supervised worker.'

    def add_arguments(self, parser):
        parser.add_argument('--watch', action='store_true')
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        while True:
            count = 0
            while count < options['limit'] and process_one(): count += 1
            if not options['watch']:
                self.stdout.write(f'Processed {count} courier callback attempts.')
                return
            time.sleep(5)

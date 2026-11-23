import time
from django.core.management.base import BaseCommand
from sanjilas.courier_directory_sync import drain_pending


class Command(BaseCommand):
    help='Resume explicitly requested complete courier location imports. Never starts an unsolicited refresh.'

    def add_arguments(self,parser): parser.add_argument('--watch',action='store_true')

    def handle(self,*args,**options):
        while True:
            drain_pending()
            if not options['watch']: return
            time.sleep(5)

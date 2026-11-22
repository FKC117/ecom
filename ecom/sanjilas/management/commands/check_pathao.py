from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from sanjilas.couriers import CourierError, Pathao


class Command(BaseCommand):
    help = 'Check sandbox authentication, pickup stores and cities without creating a shipment.'

    def handle(self, *args, **options):
        try:
            client = Pathao('sandbox')
            client.token()
            stores = client.stores().get('data', {}).get('data', [])
            cities = client.cities().get('data', {}).get('data', [])
        except (CourierError, ValidationError, ValueError) as error:
            raise CommandError(str(error)) from None
        self.stdout.write(self.style.SUCCESS(f'Sandbox authentication succeeded; {len(stores)} stores; {len(cities)} cities.'))
        for store in stores:
            self.stdout.write(f"Store ID {store.get('store_id')}: {store.get('store_name')}")

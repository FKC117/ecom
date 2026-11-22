"""Courier adapters. Credentials and OAuth tokens stay on the server."""
import hashlib
import json
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPRedirectHandler

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import CourierToken


class CourierError(Exception):
    def __init__(self, message, *, rejected=False):
        super().__init__(message)
        self.rejected = rejected


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Pathao:
    hosts = {'sandbox': 'https://courier-api-sandbox.pathao.com', 'live': 'https://api-hermes.pathao.com'}

    def __init__(self, environment):
        if environment not in self.hosts:
            raise ValidationError('Unknown courier environment.')
        self.environment = environment
        self.credentials = settings.PATHAO[environment]
        if not all(self.credentials.get(key) for key in ('client_id', 'client_secret', 'username', 'password')):
            raise ValidationError('Configure Pathao credentials for this environment in .env.')
        if environment == 'live' and not settings.PATHAO_LIVE_ENABLED:
            raise ValidationError('Live courier requests are disabled. Enable PATHAO_LIVE_ENABLED explicitly.')
        self.key = hashlib.sha256(json.dumps([environment, self.credentials], sort_keys=True).encode()).hexdigest()

    def transport(self, method, path, payload=None, token=None):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        request = Request(self.hosts[self.environment] + '/aladdin/api/v1/' + path,
                          data=json.dumps(payload).encode() if payload is not None else None,
                          headers=headers, method=method)
        try:
            with build_opener(NoRedirect).open(request, timeout=20) as response:
                body = json.load(response)
        except HTTPError as error:
            # Do not echo provider bodies: they can contain credentials or customer data.
            raise CourierError(f'Pathao returned HTTP {error.code}.', rejected=error.code in (400, 401, 403, 404, 422, 429)) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise CourierError('Pathao response unavailable. Reconcile before retrying a booking.') from None
        if not isinstance(body, dict) or body.get('type') == 'error' or body.get('code', 200) not in (200, 201, 202):
            raise CourierError('Pathao returned an unexpected response.')
        return body

    def token(self):
        # Serialize token refreshes across workers using a persistent row lock.
        with transaction.atomic():
            row, _ = CourierToken.objects.get_or_create(key=self.key, defaults={'access_token': '', 'expires_at': timezone.now()})
            row = CourierToken.objects.select_for_update().get(pk=row.pk)
            if row.access_token and row.expires_at > timezone.now() + timedelta(seconds=60):
                return row.access_token
            payload = {'client_id': self.credentials['client_id'], 'client_secret': self.credentials['client_secret']}
            if row.refresh_token:
                payload.update(grant_type='refresh_token', refresh_token=row.refresh_token)
            else:
                payload.update(grant_type='password', username=self.credentials['username'], password=self.credentials['password'])
            try:
                result = self.transport('POST', 'issue-token', payload)
            except CourierError as error:
                if not row.refresh_token or not error.rejected:
                    raise
                payload = {**self.credentials, 'grant_type': 'password'}
                result = self.transport('POST', 'issue-token', payload)
            try:
                access = result['access_token']
                refresh = result.get('refresh_token', '')
                seconds = int(result['expires_in'])
                if not isinstance(access, str) or not access or not isinstance(refresh, str) or seconds <= 0:
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                raise CourierError('Pathao returned invalid token data.') from None
            row.access_token = access
            row.refresh_token = refresh
            row.expires_at = timezone.now() + timedelta(seconds=seconds)
            row.save()
            return access

    def request(self, method, path, payload=None):
        return self.transport(method, path, payload, self.token())

    def stores(self):
        return self.request('GET', 'stores')

    def cities(self):
        return self.request('GET', 'city-list')

    def zones(self, city):
        return self.request('GET', f'cities/{int(city)}/zone-list')

    def areas(self, zone):
        return self.request('GET', f'zones/{int(zone)}/area-list')

    def price(self, payload):
        return self.request('POST', 'merchant/price-plan', payload)

    def book(self, payload):
        return self.request('POST', 'orders', payload)

    def payload(self, order, account, cleaned, merchant_id):
        return pathao_payload(order, account, cleaned, merchant_id)

    def info(self, consignment):
        return self.request('GET', f'orders/{quote(consignment, safe="")}/info')


PROVIDERS = {'pathao': Pathao}


def adapter(account):
    try:
        cls = PROVIDERS[account.provider]
    except KeyError:
        raise ValidationError('This courier provider is not supported.') from None
    return cls(account.environment)


def pathao_payload(order, account, cleaned, merchant_id):
    from .payments import summary
    from .order_protection import normalize_phone
    if order.currency.upper() != 'BDT':
        raise ValidationError('Pathao bookings require BDT orders.')
    if order.status not in ('placed', 'processing') or order.review_status in ('pending', 'rejected'):
        raise ValidationError('Only approved, unshipped orders can be booked.')
    if order.payment_method == 'delivery_advance' and not order.advance_verified:
        raise ValidationError('Verify the delivery advance before courier booking.')
    if summary(order)['simulated']:
        raise ValidationError('Orders with simulated payments cannot be booked.')
    phone = normalize_phone(order.phone)
    address = ', '.join(part.strip() for part in (order.address, order.area, order.city, order.postal_code) if part.strip())
    if not 3 <= len(order.customer_name.strip()) <= 100 or not 10 <= len(address) <= 220:
        raise ValidationError('Pathao requires a recipient name of 3–100 characters and a full address of 10–220 characters.')
    due = summary(order)['amount_due']
    if due != due.to_integral_value():
        raise ValidationError('Pathao COD must be a whole BDT amount. Amend or settle the invoice first.')
    payload = {'store_id': account.store_id, 'merchant_order_id': merchant_id,
               'recipient_name': order.customer_name.strip(), 'recipient_phone': phone,
               'recipient_address': address, 'delivery_type': cleaned['delivery_type'], 'item_type': 2,
               'item_quantity': cleaned['item_quantity'], 'item_weight': float(cleaned['item_weight']),
               'amount_to_collect': int(due), 'special_instruction': cleaned.get('special_instruction', '')}
    # Local City/Area IDs are never sent as Pathao IDs. Omit absent optional IDs.
    for key in ('recipient_city', 'recipient_zone', 'recipient_area'):
        if cleaned.get(key):
            payload[key] = cleaned[key]
    return payload

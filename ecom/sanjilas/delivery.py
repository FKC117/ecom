"""Backend-owned delivery pricing shared by checkout and staff invoices."""
from django.core.exceptions import ValidationError

def rates(site):
    return {'inside':site.delivery_inside_dhaka,'outside':site.delivery_outside_dhaka}

def charge(site,zone,custom=None):
    if zone in rates(site):return rates(site)[zone]
    if zone=='custom' and custom is not None:return custom
    raise ValidationError({'delivery_zone':'Choose a delivery area.'})

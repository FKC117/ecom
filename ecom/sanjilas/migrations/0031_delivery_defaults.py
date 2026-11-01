from django.db import migrations
from django.db.models import F

def copy_rates(apps,schema_editor):
    Site=apps.get_model('sanjilas','SiteSettings')
    Site.objects.using(schema_editor.connection.alias).update(delivery_inside_dhaka=F('shipping_fee'),delivery_outside_dhaka=F('shipping_fee'))

class Migration(migrations.Migration):
    dependencies=[('sanjilas','0030_alter_order_options_order_delivery_zone_and_more')]
    operations=[migrations.RunPython(copy_rates,migrations.RunPython.noop)]

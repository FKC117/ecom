from django.db import migrations
from django.utils import timezone
from datetime import timedelta

COPY={'draft_saving': 'Saving checkout details…', 'draft_saved': 'Checkout details saved until your cart expires.', 'draft_save_error': 'Could not save checkout details. Please keep this page open and try again.', 'draft_expired': 'Your cart expired. Saved checkout details have been cleared.'}

def configure(apps,schema_editor):
    alias=schema_editor.connection.alias
    Site=apps.get_model('sanjilas','SiteSettings');Item=apps.get_model('sanjilas','CartItem')
    Site.objects.using(alias).update(cart_reservation_minutes=10)
    deadline=timezone.now()+timedelta(minutes=10)
    Item.objects.using(alias).filter(expires_at__gt=deadline).update(expires_at=deadline)
    for name,field in [('HomePage','labels'),('SiteSettings','control_labels')]:
        Model=apps.get_model('sanjilas',name)
        for obj in Model.objects.using(alias).all():
            Model.objects.using(alias).filter(pk=obj.pk).update(**{field:{**COPY,**getattr(obj,field)}})

class Migration(migrations.Migration):
    dependencies=[('sanjilas','0048_cart_checkout_draft_cart_draft_expires_at_and_more')]
    operations=[migrations.RunPython(configure,migrations.RunPython.noop)]

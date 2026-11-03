from django.db import migrations

COPY={'tracking_title': 'Order source & activity', 'tracking_help': 'IP and browser identifiers are review signals. A browser ID can be cleared or changed; it does not identify a physical device.', 'tracking_ip': 'IP address', 'tracking_browser': 'Browser identifier', 'tracking_agent': 'Browser / user-agent', 'tracking_time': 'Recorded at', 'tracking_event': 'Activity', 'tracking_status': 'HTTP status'}

def copy(apps,schema_editor):
    Model=apps.get_model('sanjilas','SiteSettings')
    for obj in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=obj.pk).update(control_labels={**COPY,**obj.control_labels})

class Migration(migrations.Migration):
    dependencies=[('sanjilas','0054_alter_order_options_cart_browser_key_and_more')]
    operations=[migrations.RunPython(copy,migrations.RunPython.noop)]

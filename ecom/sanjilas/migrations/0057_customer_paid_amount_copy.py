from django.db import migrations


def update_copy(apps, schema_editor):
    HomePage = apps.get_model('sanjilas', 'HomePage')
    for page in HomePage.objects.using(schema_editor.connection.alias).all():
        labels = dict(page.labels or {})
        if labels.get('received') in (None, 'Payments received'):
            labels['received'] = 'Paid amount'
            HomePage.objects.using(schema_editor.connection.alias).filter(pk=page.pk).update(labels=labels)


class Migration(migrations.Migration):
    dependencies = [('sanjilas', '0056_alter_cart_browser_key_alter_commerceactivity_ip_and_more')]
    operations = [migrations.RunPython(update_copy, migrations.RunPython.noop)]

from django.db import migrations


def update_default_copy(apps, schema_editor):
    homepage = apps.get_model('sanjilas', 'HomePage')
    pages = homepage.objects.using(schema_editor.connection.alias)
    for page in pages.all():
        labels = page.labels or {}
        if labels.get('backorder', 'Available to order') == 'Available to order':
            pages.filter(pk=page.pk).update(labels={**labels, 'backorder': 'Preorder available'})


class Migration(migrations.Migration):
    dependencies = [('sanjilas', '0072_listing_validation_copy')]
    operations = [migrations.RunPython(update_default_copy, migrations.RunPython.noop)]

from django.db import migrations


def add_copy(apps, schema_editor):
    HomePage = apps.get_model('sanjilas', 'HomePage')
    for page in HomePage.objects.all():
        labels = dict(page.labels)
        labels.setdefault('sitemap', 'Sitemap')
        page.labels = labels
        page.save(update_fields=['labels'])


class Migration(migrations.Migration):
    dependencies = [('sanjilas', '0069_gallery_navigation_copy')]
    operations = [migrations.RunPython(add_copy, migrations.RunPython.noop)]

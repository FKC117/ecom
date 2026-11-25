from django.db import migrations


def merge_labels(apps, schema_editor):
    from sanjilas.ai_copy import ai_labels
    for obj in apps.get_model('sanjilas', 'SiteSettings').objects.all():
        obj.control_labels = {**ai_labels(), **obj.control_labels}
        obj.save(update_fields=['control_labels'])
    for obj in apps.get_model('sanjilas', 'HomePage').objects.all():
        obj.labels = {**ai_labels(), **obj.labels}
        obj.save(update_fields=['labels'])


class Migration(migrations.Migration):
    dependencies = [('sanjilas', '0083_aiusagecounter_sitesettings_ai_admin_daily_limit_and_more')]
    operations = [migrations.RunPython(merge_labels, migrations.RunPython.noop)]

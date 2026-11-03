from django.db import migrations


def update_copy(apps, schema_editor):
    SiteSettings = apps.get_model('sanjilas', 'SiteSettings')
    for site in SiteSettings.objects.using(schema_editor.connection.alias).all():
        labels = dict(site.control_labels or {})
        if labels.get('login_limited') in (None, 'Too many sign-in attempts. Please try again in a few minutes.'):
            labels['login_limited'] = 'Too many sign-in attempts. Please try again after 15 minutes.'
            SiteSettings.objects.using(schema_editor.connection.alias).filter(pk=site.pk).update(control_labels=labels)


class Migration(migrations.Migration):
    dependencies = [('sanjilas', '0057_customer_paid_amount_copy')]
    operations = [migrations.RunPython(update_copy, migrations.RunPython.noop)]

from django.db import migrations


def populate(apps,schema_editor):
    Model=apps.get_model('sanjilas','SiteSettings')
    for site in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=site.pk).update(control_labels={'gallery_save_another':'Save and add another',**(site.control_labels or {})})


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0066_gallery_control_copy')]
    operations=[migrations.RunPython(populate,migrations.RunPython.noop)]

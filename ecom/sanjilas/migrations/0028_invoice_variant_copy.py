from django.db import migrations


def add_copy(apps,schema_editor):
    Model=apps.get_model('sanjilas','SiteSettings')
    for obj in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=obj.pk).update(control_labels={'invoice_variant':'Variant description','invoice_edit_saved':'Invoice amended',**obj.control_labels})


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0027_invoice_edit_copy')]
    operations=[migrations.RunPython(add_copy,migrations.RunPython.noop)]

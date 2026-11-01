from django.db import migrations


def add_copy(apps,schema_editor):
    Model=apps.get_model('sanjilas','HomePage')
    for page in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=page.pk).update(labels={
            'not_for_sale':'Available by enquiry',**page.labels})


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0012_price_changed_copy')]
    operations=[migrations.RunPython(add_copy,migrations.RunPython.noop)]

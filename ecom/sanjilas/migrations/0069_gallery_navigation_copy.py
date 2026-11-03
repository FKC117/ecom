from django.db import migrations


def populate(apps,schema_editor):
    Model=apps.get_model('sanjilas','HomePage')
    for page in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=page.pk).update(labels={'gallery_previous':'Previous image','gallery_next':'Next image',**(page.labels or {})})


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0068_alter_product_slug_alter_productimage_image_alt')]
    operations=[migrations.RunPython(populate,migrations.RunPython.noop)]

from django.db import migrations


def add_copy(apps,schema_editor):
    Model=apps.get_model('sanjilas','HomePage')
    for page in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=page.pk).update(labels={
            'purchase_price_missing':'This piece is available by enquiry. Contact us for its price before ordering.',**page.labels})


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0014_alter_product_track_stock')]
    operations=[migrations.RunPython(add_copy,migrations.RunPython.noop)]

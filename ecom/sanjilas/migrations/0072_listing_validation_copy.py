from django.db import migrations


def populate(apps,schema_editor):
    Model=apps.get_model('sanjilas','HomePage')
    copy={'catalog_invalid_sort':'Choose a valid sort option.','catalog_invalid_price':'Enter a valid non-negative price.','catalog_invalid_range':'Minimum price exceeds maximum price.'}
    for obj in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=obj.pk).update(labels={**copy,**(obj.labels or {})})


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0071_catalog_listing_copy')]
    operations=[migrations.RunPython(populate,migrations.RunPython.noop)]

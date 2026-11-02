from django.db import migrations


def copy(apps,schema_editor):
    alias=schema_editor.connection.alias
    labels={'nav_categories':'Categories','all_categories':'All categories'}
    for name,field in [('HomePage','labels'),('SiteSettings','control_labels')]:
        Model=apps.get_model('sanjilas',name)
        for obj in Model.objects.using(alias).all():
            Model.objects.using(alias).filter(pk=obj.pk).update(**{field:{**labels,**getattr(obj,field)}})

class Migration(migrations.Migration):
    dependencies=[('sanjilas','0052_catalog_categories_and_skus')]
    operations=[migrations.RunPython(copy,migrations.RunPython.noop)]

from django.db import migrations

COPY = {
    'gallery_title':'Gallery images', 'gallery_add':'Add image',
    'gallery_help':'Additional product photos. Edit an image to crop it, change its order or hide it. Lower positions appear first.',
    'gallery_save_first':'Save the product first, then add gallery images here.',
    'gallery_empty':'No additional images yet.', 'gallery_position':'Position',
    'gallery_visible':'Visible', 'gallery_hidden':'Hidden',
}


def populate(apps,schema_editor):
    Model=apps.get_model('sanjilas','SiteSettings')
    for site in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=site.pk).update(control_labels={**COPY,**(site.control_labels or {})})


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0065_fashion_jewellery_copy')]
    operations=[migrations.RunPython(populate,migrations.RunPython.noop)]

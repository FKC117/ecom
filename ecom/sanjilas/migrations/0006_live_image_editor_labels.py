from django.db import migrations

NEW_LABELS = {'image_live_preview': 'Live preview', 'image_adjust_crop': 'Adjust crop', 'image_finish_crop': 'Done cropping', 'image_crop_selection': 'Image crop selection', 'image_drag_crop': 'Drag the crop box to move it, or drag its edges and corners to resize. You can also use the percentage fields or arrow keys.'}


def add_live_labels(apps, schema_editor):
    SiteSettings = apps.get_model("sanjilas", "SiteSettings")
    for obj in SiteSettings.objects.using(schema_editor.connection.alias).all():
        current = obj.control_labels if isinstance(obj.control_labels, dict) else {}
        SiteSettings.objects.using(schema_editor.connection.alias).filter(pk=obj.pk).update(control_labels={**NEW_LABELS, **current})


class Migration(migrations.Migration):
    dependencies = [("sanjilas", "0005_image_editor_labels")]
    operations = [migrations.RunPython(add_live_labels, migrations.RunPython.noop)]

from django.db import migrations


NEW_LABELS = {'edit_image': 'Edit image', 'image_editor': 'Image editor', 'image_preview': 'Preview image', 'image_apply': 'Apply edits', 'image_reset': 'Reset adjustments', 'image_saved_later': 'Edits are applied when you save the record.', 'image_crop': 'Crop', 'image_crop_help': 'Crop percentages refer to the image after rotation and flipping.', 'image_x': 'Left (%)', 'image_y': 'Top (%)', 'image_width': 'Width (%)', 'image_height': 'Height (%)', 'image_rotate': 'Rotate clockwise', 'image_flip_horizontal': 'Flip horizontally', 'image_flip_vertical': 'Flip vertically', 'image_brightness': 'Brightness', 'image_contrast': 'Contrast', 'image_resize': 'Maximum width (px)', 'image_resize_help': 'Use 0 to keep the image size. Smaller images are never enlarged.', 'image_processing': 'Preparing your image…', 'image_empty': 'Upload an image to start editing.', 'image_upload_help': 'Images are stored as WebP with smaller versions for the storefront. Animated or multi-page uploads use the first frame.', 'image_supported': 'Supported formats', 'image_upload_limit': 'Maximum upload', 'image_megabytes': 'MB', 'image_pending': 'Image edits are ready to save.', 'image_enable_edits': 'Apply the adjustments below when saving'}


def add_image_labels(apps, schema_editor):
    SiteSettings = apps.get_model("sanjilas", "SiteSettings")
    for obj in SiteSettings.objects.using(schema_editor.connection.alias).all():
        current = obj.control_labels if isinstance(obj.control_labels, dict) else {}
        SiteSettings.objects.using(schema_editor.connection.alias).filter(pk=obj.pk).update(control_labels={**NEW_LABELS, **current})


class Migration(migrations.Migration):
    dependencies = [("sanjilas", "0004_alter_collection_image_alter_homepage_hero_image_and_more")]
    operations = [migrations.RunPython(add_image_labels, migrations.RunPython.noop)]

from django.db import migrations

COPY = {
    "account_name": "Your account",
    "account_login_description": "Sign in to your account. Customers, staff and administrators use the same login.",
    "account_roles_note": "Staff and administrators are taken to the store control panel automatically.",
    "account_invalid_login": "Please check your username and password.",
    "account_title": "You’re signed in.",
    "account_description": "Your customer account area is coming soon.",
    "account_control": "Open control panel",
}


def add_copy(apps, schema_editor):
    alias = schema_editor.connection.alias
    for model_name, field, additions in [("SiteSettings", "control_labels", COPY), ("HomePage", "labels", {"nav_login": "Sign in"})]:
        Model = apps.get_model("sanjilas", model_name)
        for obj in Model.objects.using(alias).all():
            Model.objects.using(alias).filter(pk=obj.pk).update(**{field: {**additions, **getattr(obj, field)}})


class Migration(migrations.Migration):
    dependencies = [("sanjilas", "0006_live_image_editor_labels")]
    operations = [migrations.RunPython(add_copy, migrations.RunPython.noop)]

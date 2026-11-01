from django.db import migrations

def copy(apps,schema_editor):
    alias=schema_editor.connection.alias
    for name,field in [("HomePage","labels"),("SiteSettings","control_labels")]:
        Model=apps.get_model("sanjilas",name)
        for obj in Model.objects.using(alias).all():
            Model.objects.using(alias).filter(pk=obj.pk).update(**{field:{"advance_checkout_help":'After transferring the delivery charge, enter the transaction reference. Payment is counted only after staff verifies receipt.',**getattr(obj,field)}})

class Migration(migrations.Migration):
    dependencies=[("sanjilas","0039_checkout_payment_copy")]
    operations=[migrations.RunPython(copy,migrations.RunPython.noop)]

from django.db import migrations


def update_copy(apps,schema_editor):
    alias=schema_editor.connection.alias
    for name,field in [('SiteSettings','control_labels'),('HomePage','labels')]:
        Model=apps.get_model('sanjilas',name)
        for obj in Model.objects.using(alias).all():
            values={'customer_area':'Area',**getattr(obj,field)}
            if name=='HomePage':
                for key,old,new in [('customer_email','Email','Email (optional)'),('customer_postal','Postal code','Postal code (optional)'),('customer_notes','Order notes','Order notes (optional)')]:
                    if values.get(key,old)==old:values[key]=new
            Model.objects.using(alias).filter(pk=obj.pk).update(**{field:values})


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0043_order_area')]
    operations=[migrations.RunPython(update_copy,migrations.RunPython.noop)]

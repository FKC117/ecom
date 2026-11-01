from django.db import migrations

def add_copy(apps,schema_editor):
    Model=apps.get_model('sanjilas','SiteSettings')
    labels={'amount_paid':'Amount paid','manual_advance_title':'Advance payment','manual_advance_help':'Enter money already received. Leave zero for an unpaid invoice.','manual_advance_note':'Advance payment recorded when issuing invoice','manual_payment_permission':'You need permission to record payments.','manual_advance_review':'Payment method'}
    for obj in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=obj.pk).update(control_labels={**labels,**obj.control_labels})

class Migration(migrations.Migration):
    dependencies=[('sanjilas','0035_alter_order_options')]
    operations=[migrations.RunPython(add_copy,migrations.RunPython.noop)]

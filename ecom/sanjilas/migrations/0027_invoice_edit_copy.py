from django.db import migrations

COPY = {'invoice_edit': 'Edit invoice', 'invoice_edit_title': 'Amend invoice', 'invoice_edit_reason': 'Reason for amendment', 'invoice_edit_save': 'Save amendment', 'invoice_edit_stock': 'This change exceeds available stock or would consume another cart reservation.', 'invoice_stale': 'This invoice changed while you were editing. Reload it before saving.', 'invoice_history': 'Edit history', 'invoice_version': 'Version', 'invoice_before': 'Before', 'invoice_after': 'After', 'invoice_catalog_discount': 'Existing catalog discount per unit', 'invoice_catalog_price': 'Current catalog selling price', 'invoice_net_unit': 'Discounted unit price', 'invoice_edit_note': 'Changes update stock by the difference only. Invoice references remain unchanged.', 'invoice_regular_subtotal': 'Subtotal before discount', 'invoice_history_reason': 'Reason', 'invoice_history_actor': 'Changed by'}


def add_copy(apps,schema_editor):
    Model=apps.get_model('sanjilas','SiteSettings')
    for obj in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=obj.pk).update(control_labels={**COPY,**obj.control_labels})


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0026_alter_order_options_order_revision_invoicerevision')]
    operations=[migrations.RunPython(add_copy,migrations.RunPython.noop)]

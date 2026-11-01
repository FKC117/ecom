from django.db import migrations

COPY = {'manual_title': 'Manual invoice', 'manual_intro': 'Create an invoice for a phone or counter order. Catalog stock is checked when issued.', 'manual_catalog': 'Catalog item', 'manual_custom': 'Custom item', 'manual_add_catalog': 'Add catalog item', 'manual_add_custom': 'Add custom item', 'manual_name': 'Item description', 'manual_price': 'Unit price', 'manual_discount': 'Discount per unit', 'manual_preview': 'Review invoice', 'manual_issue': 'Issue invoice', 'manual_issuing': 'Issuing invoice…', 'manual_items_required': 'Add between 1 and 50 invoice items.', 'manual_quantity_error': 'Each quantity must be a whole number between 1 and 999.', 'manual_duplicate': 'This catalog item is already added. Update its quantity instead.', 'manual_review_changed': 'Invoice details or catalog prices changed. Review the invoice again before issuing.', 'manual_custom_note': 'Custom items do not change catalog stock.', 'manual_payment_note': 'Issued as cash on delivery / payable on delivery.', 'manual_customer': 'Customer name', 'manual_email': 'Email (optional)', 'manual_phone': 'Phone (optional)', 'manual_address': 'Address (optional)', 'manual_city': 'City (optional)', 'manual_postal': 'Postal code (optional)', 'manual_notes': 'Notes (optional)', 'manual_lines': 'Invoice items', 'manual_remove': 'Remove item', 'manual_back': 'Back to orders', 'manual_saved': 'Invoice issued', 'manual_open': 'Open invoice', 'manual_permission': 'Manual invoicing requires its dedicated Django permission.'}


def add_copy(apps,schema_editor):
    Model=apps.get_model('sanjilas','SiteSettings')
    for obj in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=obj.pk).update(control_labels={**COPY,**obj.control_labels})


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0023_alter_order_options_order_created_by_order_source_and_more')]
    operations=[migrations.RunPython(add_copy,migrations.RunPython.noop)]

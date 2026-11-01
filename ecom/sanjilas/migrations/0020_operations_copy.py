from django.db import migrations

COPY = {'ops_orders': 'Orders', 'ops_stock': 'Stock', 'ops_orders_intro': 'Review orders and move them through fulfilment.', 'ops_stock_intro': 'On-hand stock, live cart reservations and available units.', 'ops_customer': 'Customer', 'ops_status': 'Status', 'ops_on_hand': 'On hand', 'ops_reserved': 'Reserved', 'ops_available': 'Available', 'ops_low': 'Low stock', 'ops_untracked': 'Tracking off', 'ops_all': 'All', 'ops_sku': 'SKU', 'ops_item': 'Item', 'ops_adjust': 'Adjust stock', 'ops_delta': 'Quantity change (+ / −)', 'ops_reason': 'Reason for adjustment', 'ops_expected': 'Current stock', 'ops_reason_required': 'Enter a reason and a non-zero quantity change.', 'ops_stock_changed': 'Stock changed since you opened this form. Refresh and try again.', 'ops_movements': 'Stock history', 'ops_actor': 'Changed by', 'ops_when': 'Date', 'ops_reference': 'Order', 'ops_order_details': 'Order details', 'ops_total': 'Total', 'ops_delivery': 'Delivery address', 'ops_notes': 'Customer notes', 'ops_quantity': 'Quantity', 'ops_unit_price': 'Unit price', 'ops_subtotal': 'Subtotal', 'ops_shipping': 'Shipping', 'ops_cod': 'Cash on delivery', 'ops_confirm_status': 'Apply this order status change? Cancelling returns stock.', 'ops_low_help': 'Low-stock threshold', 'ops_open_product': 'Open product', 'ops_action': 'Action', 'ops_confirm': 'Confirm change'}


def add_copy(apps,schema_editor):
    Model=apps.get_model('sanjilas','SiteSettings')
    for row in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=row.pk).update(control_labels={**COPY,**row.control_labels})


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0019_inventorymovement_actor_inventorymovement_note_and_more')]
    operations=[migrations.RunPython(add_copy,migrations.RunPython.noop)]

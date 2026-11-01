from django.db import migrations

COPY = {'cart': 'Your bag', 'cart_open': 'Open shopping bag', 'cart_close': 'Close shopping bag', 'add_to_cart': 'Add to bag', 'adding_to_cart': 'Reserving your item…', 'added_to_cart': 'Reserved in your bag.', 'quantity': 'Quantity', 'remove': 'Remove', 'update_quantity': 'Update quantity', 'cart_empty': 'Your bag is waiting for something special.', 'cart_sign_in': 'Sign in to reserve your pieces.', 'reservation_until': 'Reserved until', 'reservation_expired': 'Reservation expired. Add this piece again to reserve available stock.', 'reservation_note': 'Items in your bag reserve stock until the time shown. Removing an item releases it immediately.', 'subtotal': 'Subtotal', 'shipping': 'Delivery', 'total': 'Total', 'checkout': 'Continue to checkout', 'customer_name': 'Full name', 'customer_email': 'Email', 'customer_phone': 'Phone', 'customer_address': 'Delivery address', 'customer_city': 'City', 'customer_postal': 'Postal code', 'customer_notes': 'Order notes', 'cod': 'Cash on delivery', 'place_order': 'Place order', 'placing_order': 'Placing your order…', 'order_success': 'Your order is placed.', 'order_number': 'Order number', 'order_status': 'Order status', 'order_history': 'Your orders', 'cancel_order': 'Cancel order', 'order_cancelled': 'Your order was cancelled and stock was returned.', 'continue_shopping': 'Continue shopping', 'cart_loading': 'Opening your bag…', 'cart_error': 'We could not complete that request. Please try again.', 'shop_login_required': 'Please sign in to use your bag.', 'shop_unavailable': 'This piece is currently unavailable for purchase.', 'shop_stock_unconfigured': 'This piece is not available for online purchase yet.', 'shop_choose_variant': 'Choose an available variant first.', 'shop_insufficient_stock': 'There is not enough available stock. Another customer may have reserved the last piece.', 'shop_currency_error': 'This piece uses a currency that is not available at checkout.', 'shop_checkout_conflict': 'Please start a new checkout.', 'shop_payment_unavailable': 'Checkout is currently unavailable.', 'shop_empty': 'Your bag is empty.', 'shop_expired': 'A reservation has expired. Remove or reserve that item again before checkout.', 'shop_cancel_denied': 'This order can no longer be cancelled here.', 'shop_invalid': 'Please check the details you entered.', 'shop_csrf': 'Refresh the page and try again.', 'shop_placed': 'Placed', 'shop_processing': 'Processing', 'shop_shipped': 'Shipped', 'shop_completed': 'Completed', 'shop_cancelled': 'Cancelled'}


def seed(apps, schema_editor):
    alias=schema_editor.connection.alias
    HomePage=apps.get_model('sanjilas','HomePage')
    for page in HomePage.objects.using(alias).all():
        HomePage.objects.using(alias).filter(pk=page.pk).update(labels={**COPY,**page.labels})
    Movement=apps.get_model('sanjilas','InventoryMovement')
    for name in ('Product','ProductVariant'):
        Model=apps.get_model('sanjilas',name)
        for row in Model.objects.using(alias).filter(stock_quantity__gt=0):
            Movement.objects.using(alias).create(product_id=row.pk if name=='Product' else row.product_id,
                variant_id=row.pk if name=='ProductVariant' else None, quantity=row.stock_quantity,reason='adjustment')


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0010_sitesettings_cart_reservation_minutes_and_more')]
    operations=[migrations.RunPython(seed,migrations.RunPython.noop)]

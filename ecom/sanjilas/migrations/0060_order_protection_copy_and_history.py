import hashlib
import json
import re
from django.db import migrations

PUBLIC = {
    'shop_order_blocked':'We cannot accept this request right now. Please contact the store for help.',
    'shop_order_limited':'Too many attempts. Please wait 10 minutes before trying again.',
    'shop_duplicate_order':'An order for these items was already placed with this phone number recently. Please check your orders or contact the store before ordering again.',
    'shop_cart_limit':'Your bag exceeds the store’s item limit. Reduce the quantity or contact the store for a larger order.',
}
STAFF = {
    'review_title':'Order review', 'review_help':'Check the customer and order details before approval. These signals do not prove fraud. Rejecting cancels the order and restores stock; any real payment still needs refund handling.',
    'review_clear':'No review needed', 'review_pending':'Needs review', 'review_approved':'Approved', 'review_rejected':'Rejected',
    'review_open_phone':'Several open orders share this phone number.',
    'review_cancelled_phone':'This phone number has several recently cancelled orders.',
    'review_busy_ip':'Several recent orders share this IP. Shared connections can be legitimate.',
    'review_shared_browser':'This browser was used by several accounts recently.',
    'review_reason':'Review reason', 'review_approve':'Approve order', 'review_reject':'Reject and cancel order',
    'review_save':'Save decision', 'review_decision':'Decision', 'review_history':'Review history',
    'review_queue':'Needs review only', 'review_stale':'This review changed. Refresh before deciding again.',
}


def populate(apps, schema_editor):
    alias = schema_editor.connection.alias
    for model_name, field, defaults in [('HomePage','labels',PUBLIC),('SiteSettings','control_labels',STAFF)]:
        model = apps.get_model('sanjilas',model_name)
        for obj in model.objects.using(alias).all():
            model.objects.using(alias).filter(pk=obj.pk).update(**{field:{**defaults,**(getattr(obj,field) or {})}})
    Order = apps.get_model('sanjilas','Order')
    Item = apps.get_model('sanjilas','OrderItem')
    for order in Order.objects.using(alias).filter(source='online').iterator():
        phone = re.sub(r'[\s().-]', '', order.phone)
        if phone.startswith('00880'): phone='0'+phone[5:]
        elif phone.startswith('+880'): phone='0'+phone[4:]
        elif phone.startswith('880'): phone='0'+phone[3:]
        if not re.fullmatch(r'01[0-9]{9}',phone): continue
        rows = sorted((row.product_id or 0,row.variant_id or 0,row.quantity) for row in Item.objects.using(alias).filter(order=order))
        fingerprint = hashlib.sha256(json.dumps([phone,rows]).encode()).hexdigest()
        Order.objects.using(alias).filter(pk=order.pk).update(normalized_phone=phone,checkout_fingerprint=fingerprint)


class Migration(migrations.Migration):
    dependencies = [('sanjilas','0059_commerceblock_commercelimit_alter_order_options_and_more')]
    operations = [migrations.RunPython(populate,migrations.RunPython.noop)]

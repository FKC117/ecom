from django.db import migrations

COPY={'payment_choice': 'Payment option', 'pay_delivery_now': 'Pay delivery charge now', 'pay_delivery_help': 'Pay only the delivery charge in advance; pay for the items on delivery.', 'cod_help': 'Pay the full amount when your order arrives.', 'advance_unavailable': 'Delivery-charge advance is not available yet.', 'advance_instructions': 'Payment instructions', 'advance_reference': 'Transaction reference', 'advance_pending': 'Delivery payment awaiting verification', 'advance_pending_help': 'Your transaction reference has been submitted. Payment is counted only after staff verifies receipt.', 'advance_verify': 'Verify delivery payment', 'advance_due_now': 'Delivery charge to pay now', 'advance_remaining': 'Remaining on delivery after verification', 'checkout_details': 'Delivery and payment details', 'advance_verify_help': 'Check the transfer before recording this payment.'}

def add_copy(apps,schema_editor):
    alias=schema_editor.connection.alias
    for name,field in [('SiteSettings','control_labels'),('HomePage','labels')]:
        Model=apps.get_model('sanjilas',name)
        for obj in Model.objects.using(alias).all():
            Model.objects.using(alias).filter(pk=obj.pk).update(**{field:{**COPY,**getattr(obj,field)}})

class Migration(migrations.Migration):
    dependencies=[('sanjilas','0038_order_advance_amount')]
    operations=[migrations.RunPython(add_copy,migrations.RunPython.noop)]

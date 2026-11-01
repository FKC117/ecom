from django.db import migrations

def opening(apps,schema_editor):
    Order=apps.get_model('sanjilas','Order');Payment=apps.get_model('sanjilas','OrderPayment')
    for order in Order.objects.using(schema_editor.connection.alias).filter(payment_status='paid',total__gt=0):
        Payment.objects.using(schema_editor.connection.alias).create(order_id=order.pk,kind='payment',amount=order.total,method='other',occurred_at=order.created_at,notes='Opening balance from previous paid status; original payment method and date were not recorded.')

class Migration(migrations.Migration):
    dependencies=[('sanjilas','0032_alter_order_payment_status_orderpayment')]
    operations=[migrations.RunPython(opening,migrations.RunPython.noop)]

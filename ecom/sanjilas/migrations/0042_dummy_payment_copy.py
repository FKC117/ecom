from django.db import migrations

COPY={'pay_now': 'Pay now', 'pay_now_help': 'Pay the full order total, including delivery.', 'pay_now_unavailable': 'Full online payment is not available yet.', 'dummy_payment_title': 'Dummy payment', 'dummy_payment_help': 'Test payment only. No money will be transferred.', 'dummy_payment_note': 'Simulated checkout payment. No actual funds received.', 'dummy_payment_submit': 'Simulate payment and place order', 'dummy_payment_completed': 'Dummy payment completed — no actual money was received.', 'pay_today': 'Pay now', 'remaining_delivery': 'Remaining on delivery', 'method_dummy': 'Dummy payment'}

def add_copy(apps,schema_editor):
    alias=schema_editor.connection.alias
    for name,field in [('SiteSettings','control_labels'),('HomePage','labels')]:
        Model=apps.get_model('sanjilas',name)
        for obj in Model.objects.using(alias).all():
            Model.objects.using(alias).filter(pk=obj.pk).update(**{field:{**COPY,**getattr(obj,field)}})

class Migration(migrations.Migration):
    dependencies=[('sanjilas','0041_orderpayment_is_simulated_and_more')]
    operations=[migrations.RunPython(add_copy,migrations.RunPython.noop)]

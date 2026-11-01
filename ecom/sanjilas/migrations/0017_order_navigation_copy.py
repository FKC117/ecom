from django.db import migrations

COPY = {'order_details': 'Order details', 'view_order': 'View order', 'back_to_orders': 'Back to orders', 'orders_empty': 'You have not placed any orders yet.', 'order_cancel_confirm': 'Cancel this order? Its items will be returned to available stock.'}


def add_copy(apps,schema_editor):
    Model=apps.get_model('sanjilas','HomePage')
    for page in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=page.pk).update(labels={**COPY,**page.labels})


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0016_order_reference_number')]
    operations=[migrations.RunPython(add_copy,migrations.RunPython.noop)]

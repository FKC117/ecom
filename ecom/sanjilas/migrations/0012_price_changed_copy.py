from django.db import migrations


def add_copy(apps,schema_editor):
    Model=apps.get_model('sanjilas','HomePage')
    for page in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=page.pk).update(labels={
            'shop_price_changed':'Prices or delivery charges changed. Review the refreshed total and place your order again.',**page.labels})


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0011_cart_copy_and_opening_stock')]
    operations=[migrations.RunPython(add_copy,migrations.RunPython.noop)]

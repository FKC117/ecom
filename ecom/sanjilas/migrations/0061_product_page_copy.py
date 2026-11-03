from django.db import migrations


COPY = {
    'product_home':'Home', 'breadcrumbs':'Breadcrumb navigation',
    'similar_products':'You may also like', 'product_zoom':'View larger image',
    'product_delivery':'Delivery & returns',
    'product_delivery_note':'Delivery charges are added at checkout based on your delivery area.',
    'product_not_found':'This piece is no longer available.',
}


def populate(apps,schema_editor):
    Model=apps.get_model('sanjilas','HomePage')
    for page in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=page.pk).update(labels={**COPY,**(page.labels or {})})


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0060_order_protection_copy_and_history')]
    operations=[migrations.RunPython(populate,migrations.RunPython.noop)]

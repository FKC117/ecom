from django.db import migrations

COPY = {
    "variants": "Choose your variant", "features": "Details & features", "material": "Material", "gemstone": "Gemstone",
    "size": "Size", "color": "Colour / finish", "care": "Care instructions", "sku": "SKU",
    "in_stock": "In stock", "sold_out": "Sold out", "backorder": "Available to order",
    "regular_price": "Regular price", "sale_price": "Your price", "from_price": "From", "gallery": "Product images",
}


def add_copy(apps, schema_editor):
    Model = apps.get_model('sanjilas', 'HomePage')
    for page in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=page.pk).update(labels={**COPY, **page.labels})


class Migration(migrations.Migration):
    dependencies = [('sanjilas', '0008_productfeature_productimage_producttag_and_more')]
    operations = [migrations.RunPython(add_copy, migrations.RunPython.noop)]

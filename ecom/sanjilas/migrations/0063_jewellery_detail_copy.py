from django.db import migrations

COPY = {
    'detail_purity':'Metal purity / hallmark', 'detail_plating':'Plating / finish',
    'detail_stone_origin':'Stone origin / treatment', 'detail_stone_colour':'Stone colour',
    'detail_color':'Colour', 'detail_dimensions':'Measurements', 'detail_weight_grams':'Weight',
    'detail_package_contents':'Package contents', 'detail_closure':'Clasp / closure',
    'detail_adjustable':'Adjustable sizing', 'detail_warranty':'Warranty / guarantee',
    'detail_yes':'Yes', 'detail_no':'No', 'weight_unit':'g',
}


def populate(apps,schema_editor):
    Model=apps.get_model('sanjilas','HomePage')
    for page in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=page.pk).update(labels={**COPY,**(page.labels or {})})


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0062_product_adjustable_product_closure_product_color_and_more')]
    operations=[migrations.RunPython(populate,migrations.RunPython.noop)]

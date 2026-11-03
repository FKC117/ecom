from django.db import migrations


def update_copy(apps,schema_editor):
    Model=apps.get_model('sanjilas','HomePage')
    replacements={'material':('Material','Base material'), 'gemstone':('Gemstone','Stones / embellishments'),
                  'detail_stone_origin':('Stone origin / treatment','Embellishment type'),
                  'detail_stone_colour':('Stone colour','Stone / bead colour')}
    for page in Model.objects.using(schema_editor.connection.alias).all():
        labels=dict(page.labels or {})
        labels.pop('detail_purity',None)
        for key,(old,new) in replacements.items():
            if labels.get(key) in (None,old): labels[key]=new
        Model.objects.using(schema_editor.connection.alias).filter(pk=page.pk).update(labels=labels)


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0064_remove_product_purity_remove_productvariant_purity_and_more')]
    operations=[migrations.RunPython(update_copy,migrations.RunPython.noop)]

from django.db import migrations

COPY={'choose_city':'Choose a city','choose_area':'Choose an area','required_fields_note':'* Required fields'}

def populate(apps,schema_editor):
    alias=schema_editor.connection.alias
    City=apps.get_model('sanjilas','City');Area=apps.get_model('sanjilas','Area');Order=apps.get_model('sanjilas','Order')
    for order in Order.objects.using(alias).exclude(city='').iterator():
        city_name=order.city.strip();area_name=order.area.strip()
        if not city_name:continue
        city,_=City.objects.using(alias).get_or_create(name=city_name)
        area=None
        if area_name:area,_=Area.objects.using(alias).get_or_create(city_id=city.pk,name=area_name)
        Order.objects.using(alias).filter(pk=order.pk).update(city_record_id=city.pk,area_record_id=area.pk if area else None)
    for name,field in [('HomePage','labels'),('SiteSettings','control_labels')]:
        Model=apps.get_model('sanjilas',name)
        for obj in Model.objects.using(alias).all():
            Model.objects.using(alias).filter(pk=obj.pk).update(**{field:{**COPY,**getattr(obj,field)}})

class Migration(migrations.Migration):
    dependencies=[('sanjilas','0045_area_city_order_area_record_area_city_and_more')]
    operations=[migrations.RunPython(populate,migrations.RunPython.noop)]

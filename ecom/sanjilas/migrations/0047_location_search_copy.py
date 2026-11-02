from django.db import migrations

COPY={'search_city': 'Type to search cities', 'search_area': 'Type to search areas', 'location_select_match': 'Select a matching location from the suggestions.', 'location_type_hint': 'Type at least one letter to search.', 'location_searching': 'Searching…', 'location_no_matches': 'No matching locations found.', 'location_search_error': 'Could not search locations. Please try typing again.', 'location_city_first': 'Select a city first.', 'location_select_hint': 'Choose a result from the suggestions.'}

def add_copy(apps,schema_editor):
    alias=schema_editor.connection.alias
    for name,field in [('HomePage','labels'),('SiteSettings','control_labels')]:
        Model=apps.get_model('sanjilas',name)
        for obj in Model.objects.using(alias).all():
            Model.objects.using(alias).filter(pk=obj.pk).update(**{field:{**COPY,**getattr(obj,field)}})

class Migration(migrations.Migration):
    dependencies=[('sanjilas','0046_location_directory')]
    operations=[migrations.RunPython(add_copy,migrations.RunPython.noop)]

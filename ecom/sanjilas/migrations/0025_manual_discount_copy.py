from django.db import migrations

COPY = {'manual_discount_total': 'Total discount', 'manual_discount_type': 'Discount type', 'manual_discount_catalog': 'Use catalog discount', 'manual_discount_fixed': 'Fixed amount per unit', 'manual_discount_percent': 'Percentage', 'manual_discount_value': 'Discount value', 'manual_discount_help': 'Manual discounts replace catalog discounts and apply to the regular unit price.', 'manual_discount_invalid': 'Discount must not exceed the unit price; percentages must be between 0 and 100.', 'manual_regular_price': 'Regular unit price'}


def add_copy(apps,schema_editor):
    Model=apps.get_model('sanjilas','SiteSettings')
    for obj in Model.objects.using(schema_editor.connection.alias).all():
        Model.objects.using(schema_editor.connection.alias).filter(pk=obj.pk).update(control_labels={**COPY,**obj.control_labels})


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0024_manual_invoice_copy')]
    operations=[migrations.RunPython(add_copy,migrations.RunPython.noop)]

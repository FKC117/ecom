from django.db import migrations

COPY = {'invoice': 'Invoice', 'print_invoice': 'Print / save PDF', 'bill_to': 'Bill to', 'invoice_date': 'Invoice date', 'invoice_discount': 'Discount', 'invoice_item': 'Item', 'invoice_sku': 'SKU', 'invoice_due': 'Payable on delivery', 'invoice_cancelled': 'Cancelled order'}


def add_copy(apps,schema_editor):
    alias=schema_editor.connection.alias
    for name,field,values in [('HomePage','labels',COPY),('SiteSettings','control_labels',{'ops_invoice':'Invoice'})]:
        Model=apps.get_model('sanjilas',name)
        for obj in Model.objects.using(alias).all():
            Model.objects.using(alias).filter(pk=obj.pk).update(**{field:{**values,**getattr(obj,field)}})


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0021_sitesettings_invoice_address_and_more')]
    operations=[migrations.RunPython(add_copy,migrations.RunPython.noop)]

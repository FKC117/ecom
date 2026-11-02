import django.db.models.deletion
import sanjilas.image_fields
import sanjilas.models
from django.db import migrations,models


def rename_legacy_storage(apps,schema_editor):
    # PostgreSQL keeps index and identity-sequence names when a table is renamed.
    q=schema_editor.quote_name
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT indexname FROM pg_indexes WHERE schemaname=current_schema() AND tablename='sanjilas_category'")
        for (name,) in cursor.fetchall():
            if name.startswith('sanjilas_collection'):
                new_name=schema_editor._create_index_name('sanjilas_category',['slug'],suffix='_like') if name.endswith('_like') else name.replace('sanjilas_collection','sanjilas_category',1)
                schema_editor.execute('ALTER INDEX '+q(name)+' RENAME TO '+q(new_name))
        cursor.execute("SELECT pg_get_serial_sequence('sanjilas_category','id')")
        sequence=cursor.fetchone()[0]
        if sequence and sequence.split('.')[-1].startswith('sanjilas_collection'):
            name=sequence.split('.')[-1]
            schema_editor.execute('ALTER SEQUENCE '+q(name)+' RENAME TO '+q(name.replace('sanjilas_collection','sanjilas_category',1)))


def populate_skus(apps,schema_editor):
    alias=schema_editor.connection.alias
    Product=apps.get_model('sanjilas','Product');Variant=apps.get_model('sanjilas','ProductVariant')
    used=set()
    for Model in [Product,Variant]:
        for value in Model.objects.using(alias).exclude(sku__isnull=True).exclude(sku='').values_list('sku',flat=True):
            code=value.strip().casefold()
            if code in used:raise RuntimeError('Duplicate SKU across the catalog; resolve before migration.')
            used.add(code)
    for obj in Product.objects.using(alias).all():
        if obj.sku and obj.sku.strip():continue
        code=f'PRD-{obj.pk:06d}';suffix=1
        while code.casefold() in used:
            suffix+=1;code=f'PRD-{obj.pk:06d}-{suffix}'
        Product.objects.using(alias).filter(pk=obj.pk).update(sku=code);used.add(code.casefold())
    Permission=apps.get_model('auth','Permission')
    for action in ['add','view','change','delete']:
        Permission.objects.using(alias).filter(content_type__app_label='sanjilas',content_type__model='category',codename=action+'_collection').update(codename=action+'_category',name='Can '+action+' category')


class Migration(migrations.Migration):
    dependencies=[('sanjilas','0051_sitesettings_invoice_generated_note')]
    operations=[
        migrations.RenameModel(old_name='Collection',new_name='Category'),
        migrations.RunPython(rename_legacy_storage,migrations.RunPython.noop),
        migrations.AlterModelOptions(name='category',options={'ordering':('position','pk'),'verbose_name_plural':'Categories'}),
        migrations.RenameField(model_name='product',old_name='collection',new_name='category'),
        migrations.CreateModel(name='Collection',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('name',models.CharField(max_length=150)),('slug',models.SlugField(unique=True)),
            ('description',models.CharField(max_length=250,blank=True)),
            ('image',sanjilas.image_fields.WebPImageField(upload_to='collections/',blank=True)),
            ('image_alt',models.CharField(max_length=250,blank=True)),
            ('position',models.PositiveIntegerField(default=0)),('is_active',models.BooleanField(default=True))
        ],options={'ordering':('position','pk')}),
        migrations.AddField(model_name='product',name='collections',field=models.ManyToManyField(to='sanjilas.collection',blank=True,related_name='products')),
        migrations.RunPython(populate_skus,migrations.RunPython.noop),
        migrations.AlterField(model_name='product',name='sku',field=models.CharField('SKU',max_length=80,unique=True,default=sanjilas.models.product_sku_default)),
        migrations.AlterField(model_name='productvariant',name='sku',field=models.CharField('SKU',max_length=80,unique=True,default=sanjilas.models.variant_sku_default)),
    ]

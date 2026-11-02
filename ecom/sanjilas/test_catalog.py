from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from import_export.admin import ImportExportModelAdmin
from tablib import Dataset

from .models import Category, Product, ProductVariant, ProductTag, ProductFeature, ProductImage


class CatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name='Rings', slug='rings')
        cls.product = Product.objects.create(name='Gold ring', slug='gold-ring', category=cls.category, price='1000.00')
        cls.owner = get_user_model().objects.create_superuser('catalog-owner', password='Catalog-test-2026')

    def test_product_sku_is_generated_required_and_unique_across_variants(self):
        self.assertTrue(self.product.sku.startswith('PRD-'))
        with self.assertRaises(ValidationError):
            ProductVariant.objects.create(product=self.product,name='Duplicate parent code',sku=self.product.sku.lower())
        variant=self.variant()
        with self.assertRaises(ValidationError):
            Product.objects.create(name='Duplicate variant code',slug='duplicate-code',category=self.category,sku=variant.sku.lower())
        self.product.sku='   '
        with self.assertRaises(ValidationError):self.product.save()

    def test_collections_are_optional_many_to_many_and_separate_from_category(self):
        from .models import Collection
        bridal=Collection.objects.create(name='Bridal Edit',slug='bridal')
        everyday=Collection.objects.create(name='Everyday Essentials',slug='everyday')
        self.product.collections.add(bridal,everyday)
        data=self.client.get('/api/home/').json()
        row=next(row for row in data['products'] if row['id']==self.product.pk)
        self.assertEqual(row['category'],self.category.pk)
        self.assertEqual(set(row['collections']),{bridal.pk,everyday.pk})
        self.assertEqual([row['name'] for row in data['categories']],['Rings'])
        bridal.is_active=False;bridal.save()
        data=self.client.get('/api/home/').json()
        self.assertEqual(len(data['products']),1)
        self.assertEqual(data['products'][0]['collections'],[everyday.pk])

    def variant(self, **values):
        return ProductVariant.objects.create(product=self.product, name='Gold / 7', sku='RG-7', **values)

    def test_discount_calculation_and_rounding(self):
        self.product.discount_type = 'percent'
        self.product.discount_value = Decimal('12.35')
        self.product.price = Decimal('123.45')
        self.product.save()
        self.assertEqual(self.product.discounted_price, Decimal('108.20'))
        self.product.discount_type = 'fixed'
        self.product.discount_value = Decimal('23.45')
        self.product.save()
        self.assertEqual(self.product.discounted_price, Decimal('100.00'))

    def test_invalid_discounts_rejected(self):
        for price, kind, value in [(None,'percent',10),(100,'percent',101),(100,'fixed',101),(100,'percent',0),(100,'none',1),(100,'fixed',-1)]:
            with self.subTest(price=price,kind=kind,value=value), self.assertRaises(ValidationError):
                Product(name='Bad',slug='bad',category=self.category,price=price,discount_type=kind,discount_value=value).save()

    def test_variant_inheritance_and_override(self):
        self.product.discount_type='percent';self.product.discount_value=10;self.product.save()
        variant=self.variant()
        self.assertEqual(variant.regular_price,Decimal('1000'))
        self.assertEqual(variant.discounted_price,Decimal('900'))
        variant.price=Decimal('1500');variant.save()
        self.assertEqual(variant.discounted_price,Decimal('1350'))
        variant.override_discount=True;variant.discount_type='fixed';variant.discount_value=250;variant.save()
        self.assertEqual(variant.discounted_price,Decimal('1250'))
        variant.discount_type='none';variant.discount_value=0;variant.save()
        self.assertEqual(variant.discounted_price,Decimal('1500'))

    def test_inherited_discount_cannot_exceed_variant_price(self):
        self.product.discount_type='fixed';self.product.discount_value=500;self.product.save()
        with self.assertRaises(ValidationError): self.variant(price=200)
        self.product.discount_value=100;self.product.save()
        self.variant(price=200)
        self.product.discount_value=300
        with self.assertRaises(ValidationError): self.product.save()

    def test_variant_discount_requires_explicit_override(self):
        with self.assertRaises(ValidationError): self.variant(discount_type='percent',discount_value=10)

    def test_stock_and_backorders(self):
        variant=self.variant()
        self.assertEqual(variant.availability,'sold_out')
        variant.allow_backorder=True;variant.save()
        self.assertEqual(variant.availability,'backorder')
        variant.stock_quantity=1;variant.save()
        self.assertEqual(variant.availability,'in_stock')
        with self.assertRaises(ValidationError):
            variant.stock_quantity=-1;variant.save()

    def test_duplicate_skus_and_names_rejected(self):
        self.variant()
        with self.assertRaises(ValidationError): ProductVariant.objects.create(product=self.product,name='Other',sku='RG-7')
        with self.assertRaises(ValidationError): ProductVariant.objects.create(product=self.product,name='Gold / 7',sku='OTHER')

    def test_public_catalog_only_exposes_active_variants_tags_and_gallery(self):
        visible=ProductTag.objects.create(name='Gift',slug='gift')
        hidden=ProductTag.objects.create(name='Internal',slug='internal',is_active=False)
        self.product.tags.set([visible,hidden])
        first=self.variant(price=1500,stock_quantity=3)
        first.tags.set([visible,hidden])
        ProductVariant.objects.create(product=self.product,name='Hidden',sku='HIDDEN',price=1,is_active=False)
        ProductVariant.objects.create(product=self.product,name='Sold out',sku='OUT',price=2)
        ProductFeature.objects.create(product=self.product,name='Purity',value='18K')
        ProductImage.objects.create(product=self.product,image='products/test.webp',image_alt='Detail')
        ProductImage.objects.create(product=self.product,image='products/hidden.webp',image_alt='Hidden',is_active=False)
        data=self.client.get('/api/home/').json()['products'][0]
        self.assertEqual(data['discounted_price'],'1500.00')
        self.assertTrue(data['has_price_range'])
        self.assertEqual([tag['name'] for tag in data['tags']],['Gift'])
        self.assertEqual(len(data['variants']),2)
        self.assertEqual(data['variants'][0]['tags'],data['tags'])
        self.assertEqual(data['features'][0]['value'],'18K')
        self.assertEqual(len(data['gallery']),1)

    def test_all_new_models_have_react_controls_and_import_export(self):
        self.client.force_login(self.owner)
        data=self.client.get('/api/control/session/').json()
        keys={item['key'] for item in data['models']}
        directory={item['key'] for item in data['models'] if item['menu_visible']}
        self.assertIn('sanjilas.product',directory)
        for model in [ProductTag,ProductFeature,ProductImage,ProductVariant]:
            self.assertIsInstance(admin.site._registry[model],ImportExportModelAdmin)
            self.assertIn(model._meta.label_lower,keys)
            self.assertNotIn(model._meta.label_lower,directory)
            if model is not ProductTag:
                metadata=next(item for item in data['models'] if item['key']==model._meta.label_lower)
                self.assertEqual(metadata['parent_field'],'product')
                self.assertEqual(metadata['parent_model'],'sanjilas.product')
            response=self.client.get(f'/api/control/models/sanjilas/{model._meta.model_name}/new/?product={self.product.pk}')
            self.assertEqual(response.status_code,200)
            self.assertFalse(response.json()['advanced'])
            if model is not ProductTag:
                self.assertEqual(next(field['value'] for field in response.json()['fields'] if field['name']=='product'),self.product.pk)

    def test_related_controls_follow_model_permissions(self):
        self.variant()
        self.client.force_login(self.owner)
        response=self.client.get(f'/api/control/models/sanjilas/product/{self.product.pk}/').json()
        self.assertIn('sanjilas.productvariant',{row['key'] for row in response['related']})
        staff=get_user_model().objects.create_user('catalog-viewer',is_staff=True)
        staff.user_permissions.add(Permission.objects.get(content_type__app_label='sanjilas',codename='view_product'))
        self.client.force_login(staff)
        response=self.client.get(f'/api/control/models/sanjilas/product/{self.product.pk}/').json()
        self.assertEqual(response['related'],[])
        self.assertEqual(self.client.get('/api/control/models/sanjilas/productvariant/').status_code,403)

    def test_variant_import_rejects_invalid_discount(self):
        from django.test import RequestFactory
        request=RequestFactory().get('/');request.user=self.owner
        resource=admin.site._registry[ProductVariant].get_import_resource_classes(request)[0]()
        data=Dataset(headers=['id','product','name','sku','price','discount_type','discount_value','override_discount'])
        data.append(['',self.product.pk,'Bad','BAD',100,'percent',120,True])
        result=resource.import_data(data,dry_run=False)
        self.assertTrue(result.has_errors() or result.has_validation_errors())
        self.assertFalse(ProductVariant.objects.filter(sku='BAD').exists())

    def test_react_admin_adds_product_and_tagged_variant(self):
        self.client.force_login(self.owner)
        tag=ProductTag.objects.create(name='Wedding',slug='wedding')
        response=self.client.post('/api/control/models/sanjilas/product/new/', {
            'name':'New ring','slug':'new-ring','category':self.category.pk,'sku':'NEW-RING',
            'price':'2500','currency':'bdt','discount_type':'percent','discount_value':'10',
            'stock_quantity':0,'position':0,'is_active':'on','tags':[tag.pk],
        })
        self.assertEqual(response.status_code,200,response.content)
        product=Product.objects.get(pk=response.json()['id'])
        self.assertEqual(product.currency,'BDT')
        self.assertEqual(list(product.tags.all()),[tag])
        response=self.client.post('/api/control/models/sanjilas/productvariant/new/', {
            'product':product.pk,'name':'Rose gold / 7','sku':'ROSE-7','size':'7','color':'Rose gold',
            'discount_type':'none','discount_value':0,'track_stock':'on','stock_quantity':5,
            'position':0,'is_active':'on','tags':[tag.pk],
        })
        self.assertEqual(response.status_code,200,response.content)
        variant=ProductVariant.objects.get(pk=response.json()['id'])
        self.assertEqual(variant.discounted_price,Decimal('2250'))
        self.assertEqual(list(variant.tags.all()),[tag])
        form=self.client.get(f'/api/control/models/sanjilas/productvariant/{variant.pk}/').json()
        self.assertIn('discounted_price',{field['name'] for field in form['readonly']})

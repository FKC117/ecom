from decimal import Decimal
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, RequestFactory
from .models import Category, Product, ProductVariant


class JewelleryDetailsTests(TestCase):
    def setUp(self):
        category=Category.objects.create(name='Rings',slug='rings')
        self.product=Product.objects.create(name='Sample ring',slug='sample-ring',category=category,price=100,stock_quantity=5,
            material='Sample alloy',size='7',color='Gold tone',plating='Sample finish',dimensions='20 mm',
            weight_grams='4.250',package_contents='One ring',adjustable=True,care_instructions='Sample care instructions')

    def test_product_specs_omit_blanks_and_show_formatted_weight(self):
        data=self.client.get('/api/shop/products/sample-ring/').json()['product']
        rows={row['key']:row['value'] for row in data['details']}
        self.assertEqual(rows['weight_grams'],'4.25 g')
        self.assertEqual(rows['adjustable'],'Yes')
        self.assertEqual(rows['size'],'7')
        self.assertNotIn('purity',rows)
        self.assertNotIn('warranty',rows)

    def test_variants_inherit_and_override_including_false(self):
        variant=ProductVariant.objects.create(product=self.product,name='Small',size='6',weight_grams='3.5',adjustable=False,stock_quantity=2)
        data=self.client.get('/api/shop/products/sample-ring/').json()['product']['variants'][0]
        rows={row['key']:row['value'] for row in data['details']}
        self.assertEqual(rows['material'],'Sample alloy')
        self.assertEqual(rows['plating'],'Sample finish')
        self.assertEqual(rows['size'],'6')
        self.assertEqual(rows['weight_grams'],'3.5 g')
        self.assertEqual(rows['adjustable'],'No')
        self.assertEqual(rows['sku'],variant.sku)
        self.assertEqual(data['care_instructions'],'Sample care instructions')
        variant.care_instructions='Variant care';variant.save()
        self.assertEqual(self.client.get('/api/shop/products/sample-ring/').json()['product']['variants'][0]['care_instructions'],'Variant care')

    def test_weight_must_be_positive(self):
        for weight in [Decimal('0'),Decimal('-1')]:
            self.product.weight_grams=weight
            with self.assertRaises(ValidationError): self.product.save()

    def test_both_admin_forms_include_structured_fields(self):
        request=RequestFactory().get('/');request.user=get_user_model().objects.create_superuser('jewellery-owner')
        for model in [Product,ProductVariant]:
            fields=admin.site._registry[model].get_form(request).base_fields
            self.assertNotIn('purity',fields)
            for name in ['plating','dimensions','weight_grams','adjustable','package_contents','warranty','size','color']:
                self.assertIn(name,fields)

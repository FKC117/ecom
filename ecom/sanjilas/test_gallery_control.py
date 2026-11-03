from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from .models import Category,Product,ProductImage


class GalleryControlTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_superuser('gallery-owner')
        category=Category.objects.create(name='Rings',slug='rings')
        self.product=Product.objects.create(name='Ring',slug='ring',category=category)
        self.image=ProductImage.objects.create(product=self.product,image='products/gallery/test.webp',image_alt='Side view',position=2)
        self.client.force_login(self.owner)

    def test_gallery_metadata_cover_labels_and_delete(self):
        data=self.client.get(f'/api/control/models/sanjilas/product/{self.product.pk}/').json()
        self.assertEqual(next(field for field in data['fields'] if field['name']=='image')['label'],'Cover image')
        gallery=next(row for row in data['related'] if row['gallery'])
        self.assertEqual(gallery['group'],'Cover image')
        self.assertTrue(gallery['can_add'])
        self.assertEqual(gallery['records'][0]['alt'],'Side view')
        self.assertEqual(gallery['records'][0]['position'],2)
        self.assertTrue(gallery['records'][0]['permissions']['delete'])
        self.assertEqual(self.client.post(f'/api/control/models/sanjilas/productimage/{self.image.pk}/delete/',{'confirm':'yes'}).status_code,200)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
        self.assertFalse(ProductImage.objects.exists())

    def test_new_products_require_save_and_child_permissions_are_respected(self):
        data=self.client.get('/api/control/models/sanjilas/product/new/').json()
        gallery=next(row for row in data['related'] if row['gallery'])
        self.assertFalse(gallery['can_add']);self.assertEqual(gallery['records'],[])
        staff=get_user_model().objects.create_user('gallery-staff',is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename='view_product',content_type__app_label='sanjilas'))
        self.client.force_login(staff)
        data=self.client.get(f'/api/control/models/sanjilas/product/{self.product.pk}/').json()
        self.assertFalse(any(row['gallery'] for row in data['related']))

    def test_add_another_keeps_parent_and_defaults_next_position(self):
        data=self.client.get(f'/api/control/models/sanjilas/productimage/new/?product={self.product.pk}&after={self.image.pk}').json()
        self.assertTrue(data['model']['repeat_add'])
        fields={field['name']:field for field in data['fields']}
        self.assertEqual(str(fields['product']['value']),str(self.product.pk))
        self.assertEqual(fields['position']['value'],3)
        self.assertFalse(fields['image']['value'])

    def test_image_alt_is_optional_and_generated_with_number(self):
        first=ProductImage.objects.create(product=self.product,image='products/gallery/one.webp')
        second=ProductImage.objects.create(product=self.product,image='products/gallery/two.webp')
        self.assertEqual(first.image_alt,'Ring 1')
        self.assertEqual(second.image_alt,'Ring 2')
        first.position=10;first.save();self.assertEqual(first.image_alt,'Ring 1')
        form=self.client.get(f'/api/control/models/sanjilas/productimage/new/?product={self.product.pk}').json()
        self.assertFalse(next(field for field in form['fields'] if field['name']=='image_alt')['required'])

    def test_product_slugs_generate_uniquely_and_remain_stable(self):
        first=Product.objects.create(name='Sample Bangle',category=self.product.category)
        second=Product.objects.create(name='Sample Bangle',category=self.product.category)
        self.assertEqual(first.slug,'sample-bangle')
        self.assertEqual(second.slug,'sample-bangle-2')
        first.name='Renamed Bangle';first.save();self.assertEqual(first.slug,'sample-bangle')
        data=self.client.get('/api/control/models/sanjilas/product/new/').json()
        self.assertNotIn('slug',[field['name'] for field in data['fields']])

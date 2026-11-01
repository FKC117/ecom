import io
import json
import tempfile
from pathlib import Path

from PIL import Image, ImageCms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings

from .image_fields import ImageInput, WebPImageFormField
from .images import image_metadata, parse_edits, prepare_image
from .models import Collection, Product, SiteSettings


def upload(size=(800,600), image_format='JPEG', mode='RGB', **kwargs):
    buffer=io.BytesIO()
    Image.new(mode,size,(100,120,140,100) if mode=='RGBA' else 'red').save(buffer,image_format,**kwargs)
    return SimpleUploadedFile('photograph.'+image_format.lower(),buffer.getvalue(),content_type='application/octet-stream')


class ImageEngineTests(SimpleTestCase):
    def test_supported_raster_formats_are_really_webp(self):
        for image_format in ('JPEG','PNG','WEBP','TIFF','BMP','GIF','AVIF','HEIF'):
            with self.subTest(image_format=image_format):
                result=prepare_image(upload((64,48),image_format))
                self.assertTrue(result.name.endswith('.webp'))
                with Image.open(result) as decoded:
                    self.assertEqual(decoded.format,'WEBP')
                    self.assertEqual(decoded.size,(64,48))

    def test_variants_keep_aspect_ratio_and_do_not_upscale(self):
        result=prepare_image(upload((1000,500)))
        self.assertEqual(set(result.derivatives),{'_320w.webp','_640w.webp','_960w.webp'})
        for suffix,data in result.derivatives.items():
            width=int(suffix.split('w')[0][1:])
            with Image.open(io.BytesIO(data)) as image:
                self.assertEqual(image.size,(width,width//2))
        self.assertFalse(prepare_image(upload((100,50))).derivatives)

    def test_orientation_metadata_alpha_and_colour_profile(self):
        exif=Image.Exif();exif[274]=6;exif[270]='Private camera information'
        result=prepare_image(upload((80,40),exif=exif))
        with Image.open(result) as image:
            self.assertEqual(image.size,(40,80))
            self.assertFalse(image.getexif())
            self.assertTrue(image.info.get('icc_profile'))
        alpha=prepare_image(upload((32,32),'PNG','RGBA'))
        with Image.open(alpha) as image:
            self.assertEqual(image.getpixel((5,5))[3],100)
        with_profile=prepare_image(upload((32,32),icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()))
        self.assertEqual(with_profile.width,32)

    def test_edit_geometry_and_adjustments(self):
        result=prepare_image(upload((800,400)),{'rotate':90,'flip_horizontal':True,'flip_vertical':True,'crop':{'x':0,'y':0,'width':.5,'height':.5},'brightness':1.1,'contrast':.9,'resize_width':100})
        self.assertEqual((result.width,result.height),(100,200))

    def test_invalid_edits_payloads_are_rejected(self):
        for edits in ('not json',[],{'rotate':45},{'brightness':float('nan')},{'contrast':2},{'flip_horizontal':'true'},{'resize_width':-1},{'unexpected':True},{'crop':{'x':.9,'y':0,'width':.5,'height':1}}):
            with self.subTest(edits=edits),self.assertRaises(ValidationError):
                parse_edits(edits)

    def test_file_content_and_resource_limits_are_checked(self):
        with self.assertRaises(ValidationError):
            prepare_image(ContentFile(b'<svg></svg>',name='pretend.jpg'))
        with override_settings(IMAGE_MAX_UPLOAD_BYTES=50), self.assertRaises(ValidationError):
            prepare_image(upload())
        with override_settings(IMAGE_MAX_PIXELS=100), self.assertRaises(ValidationError):
            prepare_image(upload((20,20)))

    def test_master_size_limit_and_icon_fallback(self):
        with override_settings(IMAGE_MAX_EDGE=400):
            result=prepare_image(upload((800,400)))
            self.assertEqual((result.width,result.height),(400,200))
        result=prepare_image(upload((300,300),'PNG','RGBA'),icon_size=180)
        self.assertEqual((result.width,result.height),(180,180))
        self.assertEqual(set(result.derivatives),{'_compat.png'})
        with Image.open(io.BytesIO(result.derivatives['_compat.png'])) as icon:
            self.assertEqual(icon.format,'PNG')


class StoredImagesTests(TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        override=override_settings(MEDIA_ROOT=self.folder.name)
        override.enable();self.addCleanup(override.disable)
        self.user=get_user_model().objects.create_user('image-editor',password='Temporary-image-test1',is_staff=True)
        self.user.user_permissions.set(Permission.objects.filter(content_type__app_label='sanjilas',codename__in=['view_collection','add_collection','change_collection','view_sitesettings','change_sitesettings']))
        self.client.force_login(self.user)
        self.obj=Collection.objects.create(name='Images',slug='images',image=upload())
        self.root='/api/control/models/sanjilas/collection/'

    def test_model_save_generates_only_webp_and_metadata(self):
        self.assertTrue(self.obj.image.name.endswith('.webp'))
        self.assertNotIn('.jpeg',self.obj.image.name)
        files=list(Path(self.folder.name).rglob('*.*'))
        self.assertEqual(len(files),3)  # 800px master, 320px and 640px variants.
        self.assertTrue(all(path.suffix=='.webp' for path in files))
        metadata=image_metadata(self.obj.image)
        self.assertEqual((metadata['width'],metadata['height']),(800,600))
        self.assertIn('320w',metadata['srcset'])
        home=self.client.get('/api/home/').json()
        self.assertEqual(home['collections'][0]['image_media']['width'],800)

    def test_preview_is_permission_checked_and_does_not_write_files(self):
        before=set(Path(self.folder.name).rglob('*.*'))
        response=self.client.post(self.root+'image/image/',{'pk':self.obj.pk,'edits':json.dumps({'rotate':90})})
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response['Content-Type'],'image/webp')
        self.assertIn('no-store',response['Cache-Control'])
        with Image.open(io.BytesIO(response.content)) as image:
            self.assertEqual(image.size,(600,800))
        self.assertEqual(before,set(Path(self.folder.name).rglob('*.*')))
        self.user.user_permissions.set(Permission.objects.filter(content_type__app_label='sanjilas',codename='view_collection'))
        self.assertEqual(self.client.post(self.root+'image/image/',{'pk':self.obj.pk}).status_code,403)

    def test_save_existing_edits_creates_version_and_retains_previous_file(self):
        old_name=self.obj.image.name
        response=self.client.post(self.root+f'{self.obj.pk}/',{'name':'Images','slug':'images','position':0,'is_active':'on','image__edits':json.dumps({'rotate':90,'resize_width':300})})
        self.assertEqual(response.status_code,200,response.content)
        self.obj.refresh_from_db()
        self.assertNotEqual(self.obj.image.name,old_name)
        self.assertTrue(self.obj.image.storage.exists(old_name))
        with self.obj.image.open('rb') as stream,Image.open(stream) as image:
            self.assertEqual(image.size,(300,400))

    def test_saved_product_crop_replaces_all_public_image_urls(self):
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='sanjilas', codename__in=['view_product', 'change_product']))
        product = Product.objects.create(name='Ring', slug='ring', collection=self.obj, image=upload((1000,667)))
        old = self.client.get('/api/home/').json()['products'][0]['image_media']
        response = self.client.post(f'/api/control/models/sanjilas/product/{product.pk}/', {
            'name': 'Ring', 'slug': 'ring', 'collection': self.obj.pk, 'currency': 'BDT',
            'discount_type': 'none', 'discount_value': '0', 'stock_quantity': '0',
            'position': 0, 'is_active': 'on', 'is_featured': 'on',
            'image__edits': json.dumps({'crop': {'x': .233, 'y': .228, 'width': .503, 'height': .436}}),
        })
        self.assertEqual(response.status_code, 200, response.content)
        response = self.client.get('/api/home/')
        self.assertIn('no-store', response['Cache-Control'])
        public = response.json()['products'][0]
        new = public['image_media']
        self.assertNotEqual(old['src'], new['src'])
        self.assertEqual(public['image'], new['src'])
        self.assertEqual((new['width'], new['height']), (503, 291))
        self.assertNotIn(old['src'], new['srcset'])
        product.refresh_from_db()
        self.assertEqual(new, image_metadata(product.image))
        for item in new['srcset'].split(', '):
            url = item.split(' ')[0]
            name = url.removeprefix('/media/')
            with product.image.storage.open(name, 'rb') as stream, Image.open(stream) as image:
                self.assertAlmostEqual(image.width/image.height, 503/291, delta=.01)

    def test_invalid_record_never_writes_prepared_files(self):
        before=set(Path(self.folder.name).rglob('*.*'))
        response=self.client.post(self.root+'new/',{'name':'Missing slug','position':0,'image':upload()})
        self.assertEqual(response.status_code,400)
        self.assertEqual(before,set(Path(self.folder.name).rglob('*.*')))

    def test_bad_image_and_clear_with_edits_fail_validation(self):
        response=self.client.post(self.root+'new/',{'name':'Bad','slug':'bad','position':0,'image':SimpleUploadedFile('bad.jpg',b'bad')})
        self.assertEqual(response.status_code,400)
        response=self.client.post(self.root+f'{self.obj.pk}/',{'name':'Images','slug':'images','position':0,'image-clear':'on','image__edits':'{"rotate":90}'})
        self.assertEqual(response.status_code,400)

    def test_django_admin_widget_and_processing(self):
        self.user.is_superuser=True;self.user.save()
        response=self.client.get(f'/admin/sanjilas/collection/{self.obj.pk}/change/')
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'image__enable_edits')
        old_name=self.obj.image.name
        response=self.client.post(f'/admin/sanjilas/collection/{self.obj.pk}/change/',{'name':'Images','slug':'images','position':0,'is_active':'on','image__enable_edits':'on','image__rotate':'90','_save':'Save'})
        self.assertEqual(response.status_code,302,response.content)
        self.obj.refresh_from_db()
        self.assertNotEqual(old_name,self.obj.image.name)
        self.assertEqual(image_metadata(self.obj.image)['width'],600)

    def test_icon_webp_storage_and_public_png_compatibility(self):
        site=SiteSettings.objects.create(favicon=upload((256,256),'PNG'))
        self.assertTrue(site.favicon.name.endswith('.webp'))
        data=self.client.get('/api/site-settings/').json()
        self.assertTrue(data['favicon'].endswith('_compat.png'))
        self.assertTrue(data['favicon_media']['src'].endswith('.webp'))

    def test_form_reports_unchanged_image_correctly(self):
        field=WebPImageFormField(required=False)
        self.assertFalse(field.has_changed(self.obj.image,ImageInput(None,'')))

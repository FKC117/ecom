import uuid
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.db.models.expressions import RawSQL
from django.db import models

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from .control_copy import control_labels
from .shop_copy import shop_labels
from .image_fields import WebPImageField


def invoice_terms_default():
    return (
        'Inspect the items and quantity in the courier’s presence before accepting delivery.\n'
        'Report any damage or wrong item to {site_name} immediately, before the courier leaves. Damage-related or wrong-item exchange claims reported after the courier leaves will not be accepted.\n'
        'Other returns or exchanges require prior approval. {site_name} will confirm the applicable request period and instructions through its official contact channels.\n'
        'For an approved return or exchange, keep the item unused and retain its original packaging, tags and invoice.'
    )


class SiteSettings(models.Model):
    class Palette(models.TextChoices):
        CHAMPAGNE = "champagne", "Champagne Gold"
        ROSE = "rose", "Rose Quartz"
        EMERALD = "emerald", "Emerald Atelier"
        SAPPHIRE = "sapphire", "Midnight Sapphire"
        PEARL = "pearl", "Pearl & Platinum"

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    site_name = models.CharField(max_length=200, default="Sanjilas")
    tagline = models.CharField(max_length=300, blank=True)
    site_url = models.URLField(blank=True, help_text="Canonical public origin, including https://.")
    logo = WebPImageField(upload_to="branding/", blank=True)
    logo_dark = WebPImageField(upload_to="branding/", blank=True)
    logo_alt = models.CharField(max_length=200, blank=True)
    favicon = WebPImageField(upload_to="branding/", blank=True, icon_size=192)
    apple_touch_icon = WebPImageField(upload_to="branding/", blank=True, icon_size=180)
    footer_text = models.CharField(max_length=500, blank=True)
    palette = models.CharField(max_length=20, choices=Palette.choices, default=Palette.CHAMPAGNE)
    default_color_mode = models.CharField(max_length=5, choices=[("light", "Light"), ("dark", "Dark")], default="light")
    contact_email = models.EmailField(blank=True)
    invoice_address = models.TextField(blank=True)
    invoice_phone = models.CharField(max_length=40, blank=True)
    invoice_note = models.TextField(blank=True)
    invoice_generated_note = models.CharField(max_length=255,default='This is a computer-generated invoice and does not require a signature.')
    invoice_terms_heading = models.CharField(max_length=150,default='Important information')
    invoice_terms = models.TextField(blank=True,default=invoice_terms_default,help_text='One invoice clause per line. Use {site_name} for the current site name. Leave blank to hide the block.')
    low_stock_threshold = models.PositiveIntegerField(default=3)
    cart_reservation_minutes = models.PositiveIntegerField(default=10, validators=[MinValueValidator(1)], help_text='A cart item reserves stock for this many minutes; viewing the cart never extends the hold.')
    order_protection_enabled = models.BooleanField(default=True)
    duplicate_order_minutes = models.PositiveIntegerField(default=10, validators=[MinValueValidator(1)])
    checkout_attempt_limit = models.PositiveIntegerField(default=10, validators=[MinValueValidator(1)], help_text='Maximum checkout submissions per account, browser or phone in a fixed 10-minute window.')
    reservation_attempt_limit = models.PositiveIntegerField(default=30, validators=[MinValueValidator(1)], help_text='Maximum reservation changes per account or browser in a fixed 10-minute window. Removing items remains allowed.')
    cart_unit_limit = models.PositiveIntegerField(default=20, validators=[MinValueValidator(1)])
    order_review_phone_limit = models.PositiveIntegerField(default=2, validators=[MinValueValidator(1)], help_text='Review another order when this many open orders already share its phone.')
    order_review_ip_limit = models.PositiveIntegerField(default=8, validators=[MinValueValidator(1)], help_text='Review orders after this many online orders from one IP in an hour; never automatically reject on IP alone.')
    shop_currency = models.CharField(max_length=3, default='BDT')
    shipping_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    delivery_inside_dhaka = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    delivery_outside_dhaka = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    dummy_payments_enabled = models.BooleanField(default=False,help_text="Simulate successful payments without moving money. Disable before connecting a real gateway.")
    delivery_advance_enabled = models.BooleanField(default=False)
    delivery_advance_instructions = models.TextField(blank=True,help_text='Payment destination and instructions shown at checkout. Required to offer delivery-charge advances.')
    delivery_advance_methods = models.JSONField(default=list,blank=True,help_text='Enabled methods: bkash, nagad, bank. Configure instructions before enabling.')
    cash_on_delivery_enabled = models.BooleanField(default=True)
    control_labels = models.JSONField(default=control_labels, help_text="React control panel labels and messages. Keep the existing keys; edit the text values.")
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.TextField(blank=True)
    meta_keywords = models.CharField(max_length=500, blank=True)
    robots = models.CharField(max_length=200, default="index, follow")
    og_title = models.CharField("Open Graph title", max_length=200, blank=True)
    og_description = models.TextField("Open Graph description", blank=True)
    og_type = models.CharField(max_length=50, default="website")
    og_image = WebPImageField(upload_to="seo/", blank=True)
    og_image_alt = models.CharField(max_length=300, blank=True)
    twitter_card = models.CharField(max_length=30, default="summary_large_image", choices=[("summary", "Summary"), ("summary_large_image", "Large image")])
    twitter_site = models.CharField(max_length=100, blank=True)
    twitter_title = models.CharField(max_length=200, blank=True)
    twitter_description = models.TextField(blank=True)
    twitter_image = WebPImageField(upload_to="seo/", blank=True)
    twitter_image_alt = models.CharField(max_length=300, blank=True)
    llms_txt = models.TextField("llms.txt", blank=True)
    llms_full_txt = models.TextField("llms-full.txt", blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site settings"
        verbose_name_plural = "Site settings"
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="site_settings_singleton")]

    def clean(self):
        super().clean()
        if not isinstance(self.delivery_advance_methods,list) or any(m not in ['bkash','nagad','bank'] for m in self.delivery_advance_methods):raise ValidationError({'delivery_advance_methods':'Choose bkash, nagad or bank.'})
        if self.delivery_advance_enabled and (not self.delivery_advance_instructions.strip() or not self.delivery_advance_methods):raise ValidationError({'delivery_advance_instructions':'Add payment instructions and at least one method before enabling.'})
        if not self.shop_currency.isascii() or not self.shop_currency.isalpha() or len(self.shop_currency)!=3:
            raise ValidationError({'shop_currency': 'Enter a three-letter currency code.'})
        self.shop_currency=self.shop_currency.upper()
        if self.pk != 1:
            raise ValidationError("Only one Site Settings record is allowed (ID 1).")
        if not isinstance(self.control_labels, dict) or any(not isinstance(self.control_labels.get(key), str) or not self.control_labels[key].strip() for key in control_labels()):
            raise ValidationError({"control_labels": "Supply non-empty text for every control panel label key."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        return cls.objects.filter(pk=1).first() or cls()

    def __str__(self):
        return self.site_name


def homepage_labels():
    return {
        **shop_labels(),
        "skip_content": "Skip to content", "navigation": "Main navigation",
        "nav_collections": "Collections", "nav_featured": "The jewellery", "nav_story": "Our story",
        "nav_login": "Sign in", "nav_contact": "Get in touch", "menu_open": "Open menu", "menu_close": "Close menu",
        "mode_light": "Switch to light mode", "mode_dark": "Switch to dark mode",
        "search_open": "Search jewellery", "search_close": "Close search",
        "search_placeholder": "Find a little something…", "search_label": "Search by name or collection",
        "search_empty": "No pieces found. Try another search.", "search_results": "Your discoveries",
        "all_collections": "All pieces", "view_piece": "Discover this piece", "close_details": "Close details",
        "variants": "Choose your variant", "features": "Details & features", "material": "Base material", "gemstone": "Stones / embellishments",
        "size": "Size", "color": "Colour / finish", "care": "Care instructions", "sku": "SKU",
        "in_stock": "In stock", "sold_out": "Sold out", "backorder": "Available to order",
        "regular_price": "Regular price", "sale_price": "Your price", "from_price": "From", "gallery": "Product images",
        "piece_inquiry": "Enquire about this piece", "price_on_request": "Price on request",
        "collection_empty": "A new chapter is on its way. Come back soon.",
        "footer_navigation": "Explore", "footer_contact": "Let’s talk jewellery",
        "footer_note": "Little details. Lasting impressions.", "back_top": "Back to top",
        "loading": "Opening our jewellery box…", "load_error": "We couldn’t open the jewellery box. Please try again.",
        "retry": "Try again", "currency_locale": "en-BD",
    }


class HomePage(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    announcement = models.CharField(max_length=250, default="A first look at our world of jewellery · The preview edit")
    hero_eyebrow = models.CharField(max_length=150, default="THE EVERYDAY, MADE EXTRAORDINARY")
    hero_title = models.CharField(max_length=250, default="Some things just\nfeel like you.")
    hero_description = models.TextField(default="A quiet kind of statement. Discover jewellery for the moments you make your own.")
    hero_cta = models.CharField(max_length=100, default="Find your piece")
    hero_secondary_cta = models.CharField(max_length=100, default="The story behind the sparkle")
    hero_image = WebPImageField(upload_to="homepage/", blank=True)
    hero_image_alt = models.CharField(max_length=250, default="Gold jewellery resting on natural stone")
    hero_caption = models.CharField(max_length=200, default="THE ART OF A LITTLE EVERYDAY LUXURY")
    collections_eyebrow = models.CharField(max_length=150, default="A LITTLE SOMETHING FOR EVERY SIDE OF YOU")
    collections_title = models.CharField(max_length=200, default="Find your kind of shine.")
    featured_eyebrow = models.CharField(max_length=150, default="THE FIRST EDIT")
    featured_title = models.CharField(max_length=200, default="Meet your new favourites.")
    featured_description = models.TextField(default="Considered details. Effortless pairings. Pieces to return to, again and again.")
    story_eyebrow = models.CharField(max_length=150, default="MORE THAN AN ACCESSORY")
    story_title = models.CharField(max_length=200, default="Jewellery is personal.\nThat’s the beautiful part.")
    story_body = models.TextField(default="The necklace you never take off. The ring that feels like a little celebration. The earrings that make an ordinary Tuesday yours.\n\nWe believe the best pieces don’t just finish an outfit. They become part of your story.")
    story_image = WebPImageField(upload_to="homepage/", blank=True)
    story_image_alt = models.CharField(max_length=250, default="A closer look at delicate jewellery and its details")
    story_cta = models.CharField(max_length=100, default="Discover the collection")
    contact_eyebrow = models.CharField(max_length=150, default="LET’S FIND YOUR SOMETHING SPECIAL")
    contact_title = models.CharField(max_length=200, default="A little guidance.\nA lot of possibilities.")
    contact_body = models.TextField(default="Choosing a gift or finding your signature piece? We’d love to help you find something that feels just right.")
    contact_cta = models.CharField(max_length=100, default="Explore the pieces")
    labels = models.JSONField(default=homepage_labels, help_text="All interface and accessibility copy. Keep the existing keys; edit their values.")

    class Meta:
        verbose_name = "Home page"
        verbose_name_plural = "Home page"
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="home_page_singleton")]

    def clean(self):
        super().clean()
        if self.pk != 1:
            raise ValidationError("Only one home page is allowed (ID 1).")
        if not isinstance(self.labels, dict) or any(not isinstance(self.labels.get(key), str) or not self.labels[key].strip() for key in homepage_labels()):
            raise ValidationError({"labels": "Supply a non-empty text value for every interface label key."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.hero_title.replace("\n", " ")


class Category(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True)
    description = models.CharField(max_length=250, blank=True)
    image = WebPImageField(upload_to="collections/", blank=True)
    image_alt = models.CharField(max_length=250, blank=True)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("position", "pk")
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Collection(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True)
    description = models.CharField(max_length=250, blank=True)
    image = WebPImageField(upload_to="collections/", blank=True)
    image_alt = models.CharField(max_length=250, blank=True)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("position", "pk")

    def __str__(self):
        return self.name


def product_sku_default():return 'PRD-'+uuid.uuid4().hex[:12].upper()

def variant_sku_default():return 'VAR-'+uuid.uuid4().hex[:12].upper()


class CatalogRecord(models.Model):
    """Validate writes from admin, imports and application code alike."""
    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if hasattr(self,'sku'):
            self.sku=(self.sku or '').strip()
            for model in [Product,ProductVariant]:
                matches=model.objects.filter(sku__iexact=self.sku)
                if model is type(self) and self.pk:matches=matches.exclude(pk=self.pk)
                if self.sku and matches.exists():raise ValidationError({'sku':'This SKU is already used by another product or variant.'})

    @classmethod
    def from_db(cls, db, field_names, values):
        obj = super().from_db(db, field_names, values)
        if 'stock_quantity' in field_names:
            obj._loaded_stock = obj.stock_quantity
        return obj

    def refresh_from_db(self, *args, **kwargs):
        super().refresh_from_db(*args, **kwargs)
        if 'stock_quantity' in self.__dict__:
            self._loaded_stock = self.stock_quantity

    @transaction.atomic
    def save(self, *args, **kwargs):
        if hasattr(self,'sku'):
            self.sku=(self.sku or '').strip()
            from django.db import connection
            with connection.cursor() as cursor:cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',[self.sku.casefold()])
        self.full_clean()
        result = super().save(*args, **kwargs)
        if hasattr(self, 'stock_quantity'):
            self._loaded_stock = self.stock_quantity
        return result


class ProductTag(CatalogRecord):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class Pricing(CatalogRecord):
    class Discount(models.TextChoices):
        NONE = 'none', 'No discount'
        PERCENT = 'percent', 'Percentage'
        FIXED = 'fixed', 'Fixed amount'

    price = models.DecimalField('Regular price', max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    discount_type = models.CharField(max_length=7, choices=Discount.choices, default=Discount.NONE)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)], help_text='Percentage or amount in the product currency. Discounted price is calculated automatically.')

    class Meta:
        abstract = True
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gte=0) | models.Q(price__isnull=True), name='%(class)s_regular_nonnegative'),
            models.CheckConstraint(condition=models.Q(discount_value__gte=0), name='%(class)s_discount_nonnegative'),
            models.CheckConstraint(condition=(models.Q(discount_type='none', discount_value=0) | models.Q(discount_type='percent', discount_value__gt=0, discount_value__lte=100) | models.Q(discount_type='fixed', discount_value__gt=0)), name='%(class)s_discount_valid'),
        ]

    def clean(self):
        super().clean()
        if self.discount_value is None:
            return
        if self.discount_type == self.Discount.NONE and self.discount_value != 0:
            raise ValidationError({'discount_value': 'Use zero when no discount is selected.'})
        if self.discount_type != self.Discount.NONE:
            if self.discount_value <= 0 or (self.discount_type == self.Discount.PERCENT and self.discount_value > 100):
                raise ValidationError({'discount_value': 'Enter a positive amount; percentages cannot exceed 100.'})
            if self.regular_price is None:
                raise ValidationError({'price': 'A regular price is required before applying a discount.'})
            if self.discount_type == self.Discount.FIXED and self.discount_value > self.regular_price:
                raise ValidationError({'discount_value': 'The discount cannot exceed the regular price.'})

    def save(self, *args, **kwargs):
        from .commerce import reserved_quantity
        with transaction.atomic():
            if isinstance(self, ProductVariant) and self.product_id:
                Product.objects.select_for_update().filter(pk=self.product_id).exists()
            previous = type(self).objects.select_for_update().filter(pk=self.pk).first() if self.pk else None
            if previous and getattr(self, '_loaded_stock', previous.stock_quantity) != previous.stock_quantity:
                raise ValidationError({'stock_quantity': 'Stock changed while this form was open. Reload before saving.'})
            if previous and isinstance(self, ProductVariant) and previous.product_id != self.product_id:
                raise ValidationError({'product': 'A saved variant cannot be moved to another product. Create a new variant instead.'})
            held = reserved_quantity(self) if previous else 0
            if held and (not self.track_stock or self.stock_quantity < held):
                raise ValidationError({'stock_quantity': 'Stock cannot be reduced below active cart reservations, or tracking disabled while stock is reserved.'})
            result = super().save(*args, **kwargs)
            stored_quantity = type(self).objects.values_list('stock_quantity', flat=True).get(pk=self.pk)
            delta = stored_quantity - (previous.stock_quantity if previous else 0)
            if delta:
                InventoryMovement.objects.create(product=self if isinstance(self, Product) else self.product,
                    variant=self if isinstance(self, ProductVariant) else None, quantity=delta, reason='adjustment', actor=getattr(self,'_stock_actor',None), note=getattr(self,'_stock_note',''))
            return result

    @property
    def regular_price(self):
        return self.price

    @property
    def discount_source(self):
        return self

    @property
    def discounted_price(self):
        price = self.regular_price
        if price is None:
            return None
        source = self.discount_source
        value = Decimal(source.discount_value)
        price = Decimal(price)
        if source.discount_type == self.Discount.PERCENT:
            price *= (Decimal(100) - value) / Decimal(100)
        elif source.discount_type == self.Discount.FIXED:
            price -= value
        return max(Decimal(0), price).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


class JewelleryDetails(models.Model):
    plating = models.CharField('Plating / finish', max_length=150, blank=True)
    stone_origin = models.CharField('Embellishment type', max_length=150, blank=True, help_text='For example kundan, glass stones, crystals or beads.')
    stone_colour = models.CharField(max_length=100, blank=True)
    dimensions = models.CharField(max_length=250, blank=True, help_text='Include units, for example pendant 20 × 12 mm or chain length 45 cm.')
    weight_grams = models.DecimalField('Weight (g)', max_digits=10, decimal_places=3, null=True, blank=True, validators=[MinValueValidator(Decimal('0.001'))])
    package_contents = models.CharField(max_length=250, blank=True, help_text='For example one ring, one pair of earrings or a three-piece set.')
    closure = models.CharField('Clasp / closure', max_length=150, blank=True)
    adjustable = models.BooleanField('Adjustable sizing', null=True, blank=True, default=None, help_text='Unknown/blank hides this detail. Variant blanks inherit the product value.')
    warranty = models.TextField('Warranty / guarantee', max_length=1000, blank=True, help_text='Only enter terms that apply to this product. Blank variants inherit product details.')

    class Meta:
        abstract = True


class Product(Pricing, JewelleryDetails):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True, help_text='Generated automatically from the product name. Existing URLs remain unchanged.')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    collections = models.ManyToManyField(Collection,blank=True,related_name="products")
    subtitle = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    currency = models.CharField(max_length=3, default="BDT", help_text="ISO currency code, e.g. BDT.")
    image = WebPImageField(upload_to="products/", blank=True)
    image_alt = models.CharField(max_length=250, blank=True)
    badge = models.CharField(max_length=50, blank=True)
    sku = models.CharField('SKU', max_length=80, unique=True,default=product_sku_default)
    tags = models.ManyToManyField(ProductTag, blank=True, related_name='products')
    material = models.CharField('Base material', max_length=150, blank=True)
    gemstone = models.CharField('Stones / embellishments', max_length=150, blank=True)
    size = models.CharField(max_length=80, blank=True)
    color = models.CharField('Colour', max_length=100, blank=True)
    care_instructions = models.TextField(blank=True)
    track_stock = models.BooleanField(default=True, help_text='When enabled, zero stock is shown as sold out. Cart items reserve stock until their expiry. Enable tracking before allowing purchases.')
    stock_quantity = models.PositiveIntegerField(default=0)
    allow_backorder = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=True)

    class Meta:
        ordering = ("position", "pk")
        constraints = Pricing.Meta.constraints + [models.CheckConstraint(condition=models.Q(discount_type__in=['none','percent']) | models.Q(price__gte=models.F('discount_value')), name='product_fixed_within_price')]

    def __str__(self):
        return self.name

    def clean(self):
        if not self.slug: self._generate_slug()
        if not self.image_alt.strip(): self.image_alt=self.name[:250]
        self.sku = self.sku.strip() if self.sku else ''
        self.currency = self.currency.strip().upper()
        super().clean()
        if len(self.currency) != 3 or not self.currency.isascii() or not self.currency.isalpha():
            raise ValidationError({'currency': 'Enter a three-letter currency code, for example BDT.'})
        if self.pk:
            for variant in self.variants.all():
                variant.product = self
                source = variant.discount_source
                if source.discount_type != self.Discount.NONE and variant.regular_price is None:
                    raise ValidationError({'price': 'A variant still needs a regular price for its discount.'})
                if source.discount_type == self.Discount.FIXED and variant.regular_price is not None and variant.regular_price < source.discount_value:
                    raise ValidationError({'price': 'A discount exceeds a variant price. Adjust the variant or its discount first.'})

    def _generate_slug(self):
        from django.utils.text import slugify
        base=slugify(self.name)[:50].strip('-') or 'product'
        candidate=base
        number=2
        while type(self).objects.filter(slug=candidate).exclude(pk=self.pk).exists():
            suffix=f'-{number}'
            candidate=base[:50-len(suffix)].rstrip('-')+suffix
            number+=1
        self.slug=candidate
        self._automatic_slug=True

    @transaction.atomic
    def save(self,*args,**kwargs):
        if not self.slug or getattr(self,'_automatic_slug',False):
            from django.db import connection
            with connection.cursor() as cursor: cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',['sanjilas-product-slugs'])
            self._generate_slug()
        try: return super().save(*args,**kwargs)
        finally: self._automatic_slug=False

    @property
    def availability(self):
        if not self.track_stock or self.stock_quantity > 0:
            return 'in_stock'
        return 'backorder' if self.allow_backorder else 'sold_out'


class ProductVariant(Pricing, JewelleryDetails):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    name = models.CharField(max_length=150, help_text='Customer-facing name, e.g. Rose gold / Size 7.')
    sku = models.CharField('SKU', max_length=80, unique=True,default=variant_sku_default)
    size = models.CharField(max_length=80, blank=True)
    color = models.CharField('Colour / finish', max_length=100, blank=True)
    material = models.CharField('Base material', max_length=150, blank=True)
    gemstone = models.CharField('Stones / embellishments', max_length=150, blank=True)
    care_instructions = models.TextField(blank=True, help_text='Leave blank to use product care instructions.')
    tags = models.ManyToManyField(ProductTag, blank=True, related_name='variants')
    override_discount = models.BooleanField(default=False, help_text='Otherwise use the parent product discount. Leave price blank to use its regular price.')
    image = WebPImageField(upload_to='variants/', blank=True)
    image_alt = models.CharField(max_length=250, blank=True)
    track_stock = models.BooleanField(default=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    allow_backorder = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('position', 'pk')
        constraints = Pricing.Meta.constraints + [models.UniqueConstraint(fields=['product', 'name'], name='variant_name_per_product')]

    def clean(self):
        self.sku = self.sku.strip() if self.sku else ''
        super().clean()
        if not self.override_discount and (self.discount_type != self.Discount.NONE or self.discount_value != 0):
            raise ValidationError({'override_discount': 'Enable override to set a variant-specific discount.'})
        if self.product_id:
            source = self.discount_source
            if source.discount_type != self.Discount.NONE and self.regular_price is None:
                raise ValidationError({'price': 'A regular price is required for the inherited discount.'})
            if source.discount_type == self.Discount.FIXED and self.regular_price is not None and source.discount_value > self.regular_price:
                raise ValidationError({'price': 'The inherited discount exceeds this variant price.'})

    @property
    def regular_price(self):
        if self.price is not None:
            return self.price
        try:
            return self.product.price if self.product_id else None
        except ObjectDoesNotExist:
            return None

    @property
    def discount_source(self):
        try:
            return self if self.override_discount or not self.product_id else self.product
        except ObjectDoesNotExist:
            return self

    @property
    def availability(self):
        if not self.track_stock or self.stock_quantity > 0:
            return 'in_stock'
        return 'backorder' if self.allow_backorder else 'sold_out'

    def __str__(self):
        return f'{self.product} / {self.name}'


class ProductFeature(CatalogRecord):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='features')
    name = models.CharField(max_length=100, help_text='For example Weight, Length, Clasp or Purity.')
    value = models.CharField(max_length=300)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('position', 'pk')
        constraints = [models.UniqueConstraint(fields=['product', 'name'], name='feature_name_per_product')]

    def __str__(self):
        return f'{self.product} / {self.name}: {self.value}'


class ProductImage(CatalogRecord):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='gallery')
    image = WebPImageField(upload_to='products/gallery/')
    image_alt = models.CharField(max_length=250, blank=True, help_text='Automatic: product name followed by an image number. Leave blank to generate it.')
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('position', 'pk')

    @transaction.atomic
    def save(self,*args,**kwargs):
        if self.product_id and not self.image_alt.strip():
            product=Product.objects.select_for_update().get(pk=self.product_id)
            number=1
            prefix=product.name[:230].rstrip()
            existing=set(type(self).objects.filter(product_id=self.product_id).exclude(pk=self.pk).values_list('image_alt',flat=True))
            while f'{prefix} {number}' in existing: number+=1
            self.image_alt=f'{prefix} {number}'
            if kwargs.get('update_fields') is not None: kwargs['update_fields']=set(kwargs['update_fields'])|{'image_alt'}
        return super().save(*args,**kwargs)

    def __str__(self):
        return f'{self.product} / {self.image_alt}'


class Cart(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='shopping_cart')
    last_ip=models.GenericIPAddressField(null=True,blank=True,editable=False)
    browser_key=models.CharField(max_length=64,blank=True,editable=False,db_index=True)
    user_agent=models.CharField(max_length=512,blank=True,editable=False)
    last_activity_at=models.DateTimeField(null=True,blank=True,editable=False)
    checkout_draft = models.JSONField(default=dict,blank=True,editable=False)
    draft_expires_at = models.DateTimeField(null=True,blank=True,editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user} / {self.pk}'


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='cart_items')
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.PROTECT, related_name='cart_items')
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ('pk',)
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name='cart_item_positive'),
            models.UniqueConstraint(fields=['cart','product','variant'], nulls_distinct=False, name='cart_item_identity'),
        ]
        indexes = [models.Index(fields=['product','variant','expires_at'])]

    def __str__(self):
        return f'{self.product} / {self.quantity}'


class City(models.Model):
    name=models.CharField(max_length=120,unique=True)
    is_active=models.BooleanField(default=True)
    class Meta:
        ordering=('name',)
        verbose_name_plural='Cities'
    def __str__(self):return self.name


class Area(models.Model):
    city=models.ForeignKey(City,on_delete=models.PROTECT,related_name='areas')
    name=models.CharField(max_length=150)
    is_active=models.BooleanField(default=True)
    class Meta:
        ordering=('city__name','name')
        constraints=[models.UniqueConstraint(fields=['city','name'],name='area_name_per_city')]
    def clean(self):
        super().clean()
        if self.pk and self.order_set.exclude(city_record_id=self.city_id).exists():
            raise ValidationError({'city':'An area used by an order cannot be moved to another city.'})
    def save(self,*args,**kwargs):
        self.full_clean()
        return super().save(*args,**kwargs)
    def __str__(self):return f'{self.city} / {self.name}' 


class Order(models.Model):
    class Status(models.TextChoices):
        PLACED = 'placed', 'Placed'
        PROCESSING = 'processing', 'Processing'
        SHIPPED = 'shipped', 'Shipped'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference_number = models.PositiveBigIntegerField(unique=True, editable=False, db_default=RawSQL("nextval('sanjilas_order_reference_seq')", ()))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='shop_orders')
    checkout_ip=models.GenericIPAddressField(null=True,blank=True,editable=False,db_index=True)
    browser_key=models.CharField(max_length=64,blank=True,editable=False,db_index=True)
    user_agent=models.CharField(max_length=512,blank=True,editable=False)
    checkout_recorded_at=models.DateTimeField(null=True,blank=True,editable=False)
    normalized_phone = models.CharField(max_length=20, blank=True, editable=False, db_index=True)
    checkout_fingerprint = models.CharField(max_length=64, blank=True, editable=False, db_index=True)
    review_status = models.CharField(max_length=10, choices=[('clear','No review needed'),('pending','Needs review'),('approved','Approved'),('rejected','Rejected')], default='clear', editable=False, db_index=True)
    review_reasons = models.JSONField(default=list, blank=True, editable=False)
    revision = models.PositiveIntegerField(default=1, editable=False)
    source = models.CharField(max_length=10, choices=[('online','Online'),('manual','Manual invoice')], default='online', editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='issued_manual_orders', editable=False)
    checkout_key = models.UUIDField(unique=True, editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLACED)
    customer_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(max_length=1000, blank=True)
    city_record=models.ForeignKey(City,null=True,blank=True,on_delete=models.PROTECT)
    area_record=models.ForeignKey(Area,null=True,blank=True,on_delete=models.PROTECT)
    area = models.CharField(max_length=150, blank=True)
    city = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=30, blank=True)
    notes = models.TextField(max_length=1000, blank=True)
    currency = models.CharField(max_length=3)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    shipping_fee = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    payment_status = models.CharField(max_length=7, choices=[('unpaid','Unpaid'),('partial','Partially paid'),('paid','Paid')], default='unpaid', editable=False)
    delivery_zone = models.CharField(max_length=10, choices=[('inside','Inside Dhaka'),('outside','Outside Dhaka'),('custom','Custom charge')], default='custom')
    advance_amount = models.DecimalField(max_digits=12,decimal_places=2,default=0,editable=False)
    advance_reference = models.CharField(max_length=150,blank=True,editable=False)
    advance_channel = models.CharField(max_length=10,blank=True,editable=False)
    advance_verified = models.BooleanField(default=False,editable=False)
    payment_method = models.CharField(max_length=20, default='cod', editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        permissions = [('create_manual_invoice', 'Can create manual invoices'),('edit_invoice','Can amend invoices'),('mark_payment','Can record invoice payments and refunds'),('view_order_tracking','Can view order IP and browser tracking'),('review_order','Can approve or reject suspicious orders')]

    def clean(self):
        super().clean()
        if self.area_record_id and self.area_record.city_id!=self.city_record_id:raise ValidationError({'area_record':'Area must belong to the selected city.'})
        if self.status in ['processing','shipped','completed'] and self.review_status in ['pending','rejected']:
            raise ValidationError({'status':'Approve this order review before fulfilment.'})
        if not self._state.adding:
            previous=type(self).objects.filter(pk=self.pk).values_list('status',flat=True).first()
            allowed={'placed':{'processing','cancelled'},'processing':{'shipped','cancelled'},'shipped':{'completed'},'completed':set(),'cancelled':set()}
            if previous and self.status!=previous and self.status not in allowed.get(previous,set()):
                raise ValidationError({'status':'This order status transition is not allowed.'})

    def save(self, *args, **kwargs):
        if not getattr(self, '_commerce_write', False):
            raise ValidationError('Orders must be created or transitioned through the order service.')
        try:
            return super().save(*args, **kwargs)
        finally:
            self._commerce_write = False

    @property
    def reference(self):
        return f'ORD-{timezone.localtime(self.created_at):%Y%m%d}-{self.reference_number+100000:06d}' if isinstance(self.reference_number,int) and self.created_at else str(self.pk)

    def __str__(self):
        return self.reference


class CommerceBlock(models.Model):
    kind = models.CharField(max_length=10, choices=[('phone','Phone'),('user','Account ID'),('browser','Browser identifier'),('ip','IP address')])
    value = models.CharField(max_length=64, help_text='Exact identifier. IP blocks also affect other people sharing that connection.')
    reason = models.CharField(max_length=500, help_text='Internal reason; never shown to customers.')
    expires_at = models.DateTimeField(help_text='Required expiry; use a temporary block and review before extending it.')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'Commerce block'

    def clean(self):
        super().clean()
        from .order_protection import normalize_phone
        from .tracking import address
        self.value = self.value.strip()
        self.reason = self.reason.strip()
        if not self.reason: raise ValidationError({'reason':'Enter an internal reason.'})
        if self.kind == 'phone':
            try: self.value = normalize_phone(self.value)
            except ValidationError as error: raise ValidationError({'value':error.messages}) from error
        elif self.kind == 'ip':
            ip = address(self.value)
            if ip is None: raise ValidationError({'value':'Enter a valid IP address.'})
            self.value = str(ip)
        elif self.kind == 'browser':
            if len(self.value)!=64 or any(c not in '0123456789abcdef' for c in self.value): raise ValidationError({'value':'Enter the full browser identifier shown in order tracking.'})
        elif self.kind == 'user':
            if not self.value.isdecimal() or not self.value or int(self.value)<1: raise ValidationError({'value':'Enter a valid account ID.'})
            self.value = str(int(self.value))

    def save(self,*args,**kwargs):
        self.full_clean()
        return super().save(*args,**kwargs)

    def __str__(self): return f'{self.get_kind_display()}: {self.value}'


class CommerceLimit(models.Model):
    key = models.CharField(max_length=64, unique=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = 'Commerce rate counter'

    def __str__(self): return self.key


class OrderReview(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='reviews')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    decision = models.CharField(max_length=10, choices=[('approved','Approved'),('rejected','Rejected')])
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at','-pk')

    def save(self,*args,**kwargs):
        if not self._state.adding or not getattr(self,'_review_write',False): raise ValidationError('Use the order review service.')
        return super().save(*args,**kwargs)

    def delete(self,*args,**kwargs): raise ValidationError('Order review history cannot be deleted.')

    def __str__(self): return f'{self.order}: {self.get_decision_display()}'


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='items')
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.PROTECT)
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.PROTECT)
    product_name = models.CharField(max_length=200)
    variant_name = models.CharField(max_length=150, blank=True)
    sku = models.CharField(max_length=80, blank=True)
    quantity = models.PositiveIntegerField()
    discount_mode = models.CharField(max_length=7,choices=[('fixed','Fixed amount per unit'),('percent','Percentage')],default='fixed')
    discount_input = models.DecimalField(max_digits=12,decimal_places=2,default=0)
    regular_price = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    image_url = models.CharField(max_length=500, blank=True)

    def __str__(self):
        return f'{self.product_name} / {self.variant_name} / {self.quantity}'


class InventoryMovement(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.PROTECT)
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='inventory_adjustments')
    note = models.CharField(max_length=500, blank=True)
    quantity = models.IntegerField(help_text='Positive adds stock; negative removes it. Cart holds do not change on-hand stock.')
    reason = models.CharField(max_length=20, choices=[('adjustment','Stock adjustment'),('sale','Order placed'),('cancellation','Order cancelled')])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.product} / {self.quantity:+d} / {self.reason}'


class InvoiceRevision(models.Model):
    order = models.ForeignKey(Order,on_delete=models.PROTECT,related_name='revisions')
    version = models.PositiveIntegerField()
    operation_key = models.UUIDField(unique=True,default=uuid.uuid4,editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT)
    reason = models.CharField(max_length=500)
    before = models.JSONField()
    after = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-version',)
        constraints = [models.UniqueConstraint(fields=['order','version'],name='invoice_revision_version')]

    def save(self,*args,**kwargs):
        if not self._state.adding:
            raise ValidationError('Invoice history cannot be changed.')
        return super().save(*args,**kwargs)

    def delete(self,*args,**kwargs):
        raise ValidationError('Invoice history cannot be deleted.')

    def __str__(self):
        return f'{self.order} / {self.version}'


class OrderPayment(models.Model):
    order = models.ForeignKey(Order,on_delete=models.PROTECT,related_name='payments')
    operation_key = models.UUIDField(default=uuid.uuid4,unique=True,editable=False)
    kind = models.CharField(max_length=7,choices=[('payment','Payment'),('refund','Refund')])
    amount = models.DecimalField(max_digits=14,decimal_places=2,validators=[MinValueValidator(Decimal('0.01'))])
    method = models.CharField(max_length=10,choices=[('cash','Cash'),('bkash','bKash'),('nagad','Nagad'),('bank','Bank transfer'),('card','Card'),('other','Other'),('dummy','Dummy payment')])
    is_simulated = models.BooleanField(default=False,editable=False)
    reference = models.CharField(max_length=150,blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT)
    notes = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering=('created_at','pk')
        constraints=[models.CheckConstraint(condition=models.Q(amount__gt=0),name='order_payment_positive')]

    def save(self,*args,**kwargs):
        if not self._state.adding or not getattr(self,'_payment_write',False):
            raise ValidationError('Use the payment service to record payments and refunds.')
        return super().save(*args,**kwargs)

    def delete(self,*args,**kwargs):
        raise ValidationError('Payment records cannot be deleted. Record a refund or correcting payment.')

    def __str__(self):return f'{self.order} / {self.kind} / {self.amount}'


class CommerceActivity(models.Model):
    user=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL)
    cart=models.ForeignKey(Cart,null=True,blank=True,on_delete=models.SET_NULL)
    order=models.ForeignKey(Order,null=True,blank=True,on_delete=models.SET_NULL)
    kind=models.CharField(max_length=20,choices=[('cart_view','Cart viewed'),('cart_change','Cart reservation attempt'),('checkout','Checkout attempt')])
    ip=models.GenericIPAddressField(null=True,blank=True,db_index=True)
    browser_key=models.CharField(max_length=64,db_index=True)
    user_agent=models.CharField(max_length=512,blank=True)
    response_status=models.PositiveSmallIntegerField()
    created_at=models.DateTimeField(auto_now_add=True,db_index=True)
    class Meta:
        ordering=('-created_at','-pk')
        verbose_name_plural='Commerce activity'
    def save(self,*args,**kwargs):
        if not self._state.adding or not getattr(self,'_tracking_write',False):raise ValidationError('Activity records are written by the tracking service.')
        return super().save(*args,**kwargs)
    def delete(self,*args,**kwargs):raise ValidationError('Use the retention cleanup command to remove expired tracking data.')
    def __str__(self):return f'{self.get_kind_display()} / {self.response_status} / {self.created_at}'

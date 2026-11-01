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
    low_stock_threshold = models.PositiveIntegerField(default=3)
    cart_reservation_minutes = models.PositiveIntegerField(default=20, validators=[MinValueValidator(1)], help_text='A cart item reserves stock for this many minutes; viewing the cart never extends the hold.')
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
        "variants": "Choose your variant", "features": "Details & features", "material": "Material", "gemstone": "Gemstone",
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


class CatalogRecord(models.Model):
    """Validate writes from admin, imports and application code alike."""
    class Meta:
        abstract = True

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

    def save(self, *args, **kwargs):
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


class Product(Pricing):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    collection = models.ForeignKey(Collection, on_delete=models.PROTECT, related_name="products")
    subtitle = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    currency = models.CharField(max_length=3, default="BDT", help_text="ISO currency code, e.g. BDT.")
    image = WebPImageField(upload_to="products/", blank=True)
    image_alt = models.CharField(max_length=250, blank=True)
    badge = models.CharField(max_length=50, blank=True)
    sku = models.CharField('SKU', max_length=80, unique=True, null=True, blank=True)
    tags = models.ManyToManyField(ProductTag, blank=True, related_name='products')
    material = models.CharField(max_length=150, blank=True)
    gemstone = models.CharField(max_length=150, blank=True)
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
        self.sku = self.sku.strip() if self.sku and self.sku.strip() else None
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

    @property
    def availability(self):
        if not self.track_stock or self.stock_quantity > 0:
            return 'in_stock'
        return 'backorder' if self.allow_backorder else 'sold_out'


class ProductVariant(Pricing):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    name = models.CharField(max_length=150, help_text='Customer-facing name, e.g. Rose gold / Size 7.')
    sku = models.CharField('SKU', max_length=80, unique=True)
    size = models.CharField(max_length=80, blank=True)
    color = models.CharField('Colour / finish', max_length=100, blank=True)
    material = models.CharField(max_length=150, blank=True)
    gemstone = models.CharField(max_length=150, blank=True)
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
    image_alt = models.CharField(max_length=250)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('position', 'pk')

    def __str__(self):
        return f'{self.product} / {self.image_alt}'


class Cart(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='shopping_cart')
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
    revision = models.PositiveIntegerField(default=1, editable=False)
    source = models.CharField(max_length=10, choices=[('online','Online'),('manual','Manual invoice')], default='online', editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='issued_manual_orders', editable=False)
    checkout_key = models.UUIDField(unique=True, editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLACED)
    customer_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(max_length=1000, blank=True)
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
        permissions = [('create_manual_invoice', 'Can create manual invoices'),('edit_invoice','Can amend invoices'),('mark_payment','Can record invoice payments and refunds')]

    def clean(self):
        super().clean()
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

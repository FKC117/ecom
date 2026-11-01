from django.apps import apps
from django.contrib import admin
from django import forms
from django.db import models
from import_export.admin import ImportExportModelAdmin
from .models import SiteSettings, HomePage, Collection, Product, ProductVariant, ProductTag, ProductFeature, ProductImage, Cart, CartItem, Order, OrderItem, InventoryMovement, InvoiceRevision, OrderPayment
from .resources import SiteSettingsResource, HomePageResource


@admin.register(SiteSettings)
class SiteSettingsAdmin(ImportExportModelAdmin):
    search_fields = ("site_name", "site_url")
    resource_classes = [SiteSettingsResource]
    list_display = ("site_name", "site_url", "updated_at")
    readonly_fields = ("updated_at",)
    fieldsets = (
        ("Branding", {"fields": ("site_name", "tagline", "site_url", "logo", "logo_dark", "logo_alt", "favicon", "apple_touch_icon", "footer_text")}),
        ("Theme and contact", {"fields": ("palette", "default_color_mode", "contact_email")}),
        ("Invoice details", {"fields": ("invoice_address", "invoice_phone", "invoice_note")}),
        ("Checkout & reservations", {"fields": ("low_stock_threshold", "cart_reservation_minutes", "shop_currency", "delivery_inside_dhaka", "delivery_outside_dhaka", "cash_on_delivery_enabled", "dummy_payments_enabled", "delivery_advance_enabled", "delivery_advance_instructions", "delivery_advance_methods")}),
        ("React control panel text", {"fields": ("control_labels",)}),
        ("SEO", {"fields": ("meta_title", "meta_description", "meta_keywords", "robots")}),
        ("Open Graph / social sharing", {"fields": ("og_title", "og_description", "og_type", "og_image", "og_image_alt")}),
        ("Twitter / X", {"fields": ("twitter_card", "twitter_site", "twitter_title", "twitter_description", "twitter_image", "twitter_image_alt")}),
        ("LLM documents", {"fields": ("llms_txt", "llms_full_txt")}),
        ("Record", {"fields": ("updated_at",)}),
    )

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(HomePage)
class HomePageAdmin(ImportExportModelAdmin):
    search_fields = ("hero_title", "announcement")
    resource_classes = [HomePageResource]
    fieldsets = (
        ("Announcement", {"fields": ("announcement",)}),
        ("Hero", {"fields": ("hero_eyebrow", "hero_title", "hero_description", "hero_cta", "hero_secondary_cta", "hero_image", "hero_image_alt", "hero_caption")}),
        ("Collections", {"fields": ("collections_eyebrow", "collections_title")}),
        ("Featured jewellery", {"fields": ("featured_eyebrow", "featured_title", "featured_description")}),
        ("Story", {"fields": ("story_eyebrow", "story_title", "story_body", "story_image", "story_image_alt", "story_cta")}),
        ("Contact", {"fields": ("contact_eyebrow", "contact_title", "contact_body", "contact_cta")}),
        ("Interface text", {"fields": ("labels",)}),
    )

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not HomePage.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Collection)
class CollectionAdmin(ImportExportModelAdmin):
    search_fields = ("name", "description")
    list_display = ("name", "position", "is_active")
    list_editable = ("position", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(ImportExportModelAdmin):
    list_display = ("name", "sku", "collection", "price", "discounted_price", "currency", "is_featured", "is_active")
    list_filter = ("collection", "is_active", "is_featured")
    search_fields = ("name", "description", "sku")
    readonly_fields = ("discounted_price",)
    fieldsets = (
        ('Product', {'fields': ('name', 'slug', 'collection', 'sku', 'subtitle', 'description')}),
        ('Pricing & discount', {'fields': ('price', 'currency', 'discount_type', 'discount_value', 'discounted_price')}),
        ('Details & tagging', {'fields': ('material', 'gemstone', 'care_instructions', 'tags')}),
        ('Images', {'fields': ('image', 'image_alt')}),
        ('Stock', {'fields': ('track_stock', 'stock_quantity', 'allow_backorder')}),
        ('Storefront', {'fields': ('badge', 'position', 'is_active', 'is_featured')}),
    )
    formfield_overrides = {models.ManyToManyField: {"widget": forms.CheckboxSelectMultiple}}
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ProductVariant)
class ProductVariantAdmin(ImportExportModelAdmin):
    control_menu = False
    control_parent_field = "product"
    list_display = ('name', 'product', 'sku', 'regular_price', 'discounted_price', 'stock_quantity', 'is_active')
    list_filter = ('is_active', 'product', 'track_stock')
    search_fields = ('name', 'sku', 'product__name', 'size', 'color', 'material')
    readonly_fields = ('regular_price', 'discounted_price')
    fieldsets = (
        ('Variant', {'fields': ('product', 'name', 'sku', 'size', 'color', 'material', 'gemstone', 'tags')}),
        ('Pricing & discount', {'fields': ('price', 'regular_price', 'override_discount', 'discount_type', 'discount_value', 'discounted_price')}),
        ('Image', {'fields': ('image', 'image_alt')}),
        ('Stock & visibility', {'fields': ('track_stock', 'stock_quantity', 'allow_backorder', 'position', 'is_active')}),
    )
    formfield_overrides = {models.ManyToManyField: {"widget": forms.CheckboxSelectMultiple}}


@admin.register(ProductTag)
class ProductTagAdmin(ImportExportModelAdmin):
    control_menu = False
    list_display = ('name', 'is_active')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(ProductFeature)
class ProductFeatureAdmin(ImportExportModelAdmin):
    control_menu = False
    control_parent_field = "product"
    list_display = ('product', 'name', 'value', 'position')
    search_fields = ('product__name', 'name', 'value')


@admin.register(ProductImage)
class ProductImageAdmin(ImportExportModelAdmin):
    control_menu = False
    control_parent_field = "product"
    list_display = ('product', 'image_alt', 'position', 'is_active')
    search_fields = ('product__name', 'image_alt')


class ReadOnlyCommerceAdmin(ImportExportModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_import_permission(self, request):
        return False


@admin.register(Cart)
class CartAdmin(ReadOnlyCommerceAdmin):
    list_display = ('id', 'user', 'created_at')
    search_fields = ('user__username',)


@admin.register(CartItem)
class CartItemAdmin(ReadOnlyCommerceAdmin):
    control_menu = False
    control_parent_field = 'cart'
    list_display = ('cart', 'product', 'variant', 'quantity', 'expires_at')


@admin.register(Order)
class OrderAdmin(ImportExportModelAdmin):
    control_workspace = "orders"
    list_display = ('reference', 'customer_name', 'status', 'payment_status', 'delivery_zone', 'total', 'currency', 'created_at')
    list_filter = ('status','payment_status','delivery_zone')
    search_fields = ('id', 'customer_name', 'email', 'phone')

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields if field.name != 'status')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_import_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        from .commerce import transition_order
        transition_order(obj.pk, obj.status, actor=request.user)


@admin.register(OrderItem)
class OrderItemAdmin(ReadOnlyCommerceAdmin):
    control_menu = False
    control_parent_field = 'order'
    list_display = ('order', 'product_name', 'variant_name', 'quantity', 'unit_price', 'line_total')


@admin.register(InventoryMovement)
class InventoryMovementAdmin(ReadOnlyCommerceAdmin):
    list_display = ('product', 'variant', 'quantity', 'reason', 'order', 'created_at')
    list_filter = ('reason',)
    search_fields = ('product__name', 'variant__sku')


@admin.register(InvoiceRevision)
class InvoiceRevisionAdmin(ReadOnlyCommerceAdmin):
    control_menu = False
    control_parent_field = 'order'
    list_display = ('order', 'version', 'actor', 'reason', 'created_at')

    def get_queryset(self,request):
        return super().get_queryset(request).filter(order__in=admin.site._registry[Order].get_queryset(request))

    def has_view_permission(self,request,obj=None):
        allowed=super().has_view_permission(request,obj)
        if obj is None:return allowed
        ma=admin.site._registry[Order]
        return allowed and ma.has_module_permission(request) and ma.has_view_or_change_permission(request,obj.order)


@admin.register(OrderPayment)
class OrderPaymentAdmin(InvoiceRevisionAdmin):
    list_display=('order','kind','amount','method','is_simulated','occurred_at','actor')


for model in apps.get_app_config("sanjilas").get_models():
    if not admin.site.is_registered(model):
        admin.site.register(model, ImportExportModelAdmin)

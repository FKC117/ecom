from django.apps import apps
from django.contrib import admin
from django import forms
from django.db import models
from import_export.admin import ImportExportModelAdmin
from .models import SiteSettings, HomePage, Category, Collection, Product, ProductVariant, ProductTag, ProductFeature, ProductImage, Cart, CartItem, Order, OrderItem, InventoryMovement, InvoiceRevision, OrderPayment, CommerceActivity
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
        ("Invoice details", {"fields": ("invoice_address", "invoice_phone", "invoice_note", "invoice_generated_note", "invoice_terms_heading", "invoice_terms")}),
        ("Checkout & reservations", {"fields": ("low_stock_threshold", "cart_reservation_minutes", "shop_currency", "delivery_inside_dhaka", "delivery_outside_dhaka", "cash_on_delivery_enabled", "dummy_payments_enabled", "delivery_advance_enabled", "delivery_advance_instructions", "delivery_advance_methods")}),
        ("Order protection", {"fields": ("order_protection_enabled", "duplicate_order_minutes", "checkout_attempt_limit", "reservation_attempt_limit", "cart_unit_limit", "order_review_phone_limit", "order_review_ip_limit")}),
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
        ("Category section", {"fields": ("collections_eyebrow", "collections_title")}),
        ("Featured jewellery", {"fields": ("featured_eyebrow", "featured_title", "featured_description")}),
        ("Story", {"fields": ("story_eyebrow", "story_title", "story_body", "story_image", "story_image_alt", "story_cta")}),
        ("Contact", {"fields": ("contact_eyebrow", "contact_title", "contact_body", "contact_cta")}),
        ("Interface text", {"fields": ("labels",)}),
    )

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not HomePage.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Category)
class CategoryAdmin(ImportExportModelAdmin):
    search_fields = ("name", "description")
    list_display = ("name", "position", "is_active")
    list_editable = ("position", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Collection)
class CollectionAdmin(CategoryAdmin):
    pass


@admin.register(Product)
class ProductAdmin(ImportExportModelAdmin):
    list_display = ("name", "sku", "category", "price", "discounted_price", "currency", "is_featured", "is_active")
    list_filter = ("category", "collections", "is_active", "is_featured")
    search_fields = ("name", "description", "sku")
    readonly_fields = ("discounted_price",)
    fieldsets = (
        ('Product', {'fields': ('name', 'slug', 'category', 'collections', 'sku', 'subtitle', 'description')}),
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


class TrackingFieldsMixin:
    tracking_fields={'checkout_ip','browser_key','user_agent','checkout_recorded_at','last_ip','last_activity_at'}
    def get_search_fields(self,request):
        fields=list(super().get_search_fields(request))
        if request.user.has_perm('sanjilas.view_order_tracking'):
            fields += [field.name for field in self.model._meta.fields if field.name in {'checkout_ip','last_ip','browser_key'}]
        return fields
    def get_fields(self,request,obj=None):
        fields=super().get_fields(request,obj)
        return fields if request.user.has_perm('sanjilas.view_order_tracking') else [name for name in fields if name not in self.tracking_fields]
    def get_readonly_fields(self,request,obj=None):
        fields=super().get_readonly_fields(request,obj)
        return fields if request.user.has_perm('sanjilas.view_order_tracking') else [name for name in fields if name not in self.tracking_fields]
    def has_export_permission(self,request):
        return request.user.has_perm('sanjilas.view_order_tracking') and super().has_export_permission(request)


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
class CartAdmin(TrackingFieldsMixin,ReadOnlyCommerceAdmin):
    list_display = ('id', 'user', 'created_at')
    search_fields = ('user__username',)


@admin.register(CartItem)
class CartItemAdmin(ReadOnlyCommerceAdmin):
    control_menu = False
    control_parent_field = 'cart'
    list_display = ('cart', 'product', 'variant', 'quantity', 'expires_at')


@admin.register(Order)
class OrderAdmin(TrackingFieldsMixin,ImportExportModelAdmin):
    control_workspace = "orders"
    list_display = ('reference', 'customer_name', 'status', 'payment_status', 'delivery_zone', 'total', 'currency', 'created_at')
    list_filter = ('status','payment_status','delivery_zone','review_status')
    search_fields = ('id', 'customer_name', 'email', 'phone')

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields if field.name != 'status' and (request.user.has_perm('sanjilas.view_order_tracking') or field.name not in self.tracking_fields))

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


@admin.register(CommerceActivity)
class CommerceActivityAdmin(ReadOnlyCommerceAdmin):
    list_display=('kind','ip','user','order','response_status','created_at')
    list_filter=('kind','response_status')
    search_fields=('ip','browser_key','user__username')
    def get_queryset(self,request):
        rows=super().get_queryset(request)
        if request.user.is_superuser:return rows
        from django.db.models import Q
        oma=admin.site._registry[Order];cma=admin.site._registry[Cart]
        orders=[obj.pk for obj in oma.get_queryset(request) if oma.has_view_or_change_permission(request,obj)] if oma.has_module_permission(request) and oma.has_view_or_change_permission(request) else []
        carts=[obj.pk for obj in cma.get_queryset(request) if cma.has_view_or_change_permission(request,obj)] if cma.has_module_permission(request) and cma.has_view_or_change_permission(request) else []
        return rows.filter(Q(order__in=orders)|Q(order__isnull=True,cart__in=carts,user__isnull=False)) if request.user.has_perm('sanjilas.view_order_tracking') else rows.none()
    def has_view_permission(self,request,obj=None):
        if not request.user.has_perm('sanjilas.view_order_tracking') or not super().has_view_permission(request,obj):return False
        if obj is None:return True
        if obj.order_id:
            ma=admin.site._registry[Order]
            return ma.has_module_permission(request) and ma.has_view_or_change_permission(request,obj.order)
        if obj.cart_id:
            ma=admin.site._registry[Cart]
            return ma.has_module_permission(request) and ma.has_view_or_change_permission(request,obj.cart)
        return request.user.is_superuser


from .models import CommerceBlock, CommerceLimit, OrderReview


@admin.register(CommerceBlock)
class CommerceBlockAdmin(ImportExportModelAdmin):
    list_display = ('kind','value','reason','expires_at','is_active')
    list_filter = ('kind','is_active')
    search_fields = ('value','reason')
    readonly_fields = ('created_at',)


@admin.register(CommerceLimit)
class CommerceLimitAdmin(ReadOnlyCommerceAdmin):
    list_display = ('key','count','expires_at')


@admin.register(OrderReview)
class OrderReviewAdmin(InvoiceRevisionAdmin):
    list_display = ('order','decision','actor','reason','created_at')


from axes.models import AccessAttempt, AccessLog, AccessFailureLog
from axes.admin import AccessAttemptAdmin, AccessLogAdmin, AccessFailureLogAdmin


class LoginSecurityAdminMixin:
    """System-generated records: review/export, and permission-controlled cleanup."""
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_import_permission(self, request):
        return False


@admin.register(AccessAttempt)
class LoginAttemptAdmin(LoginSecurityAdminMixin, AccessAttemptAdmin, ImportExportModelAdmin):
    # Avoid colliding with the optional reverse OneToOne relation of this name.
    readonly_fields = [name if name != 'expiration' else 'attempt_expiration' for name in AccessAttemptAdmin.readonly_fields]
    fieldsets = tuple((title, {**options, 'fields': tuple('attempt_expiration' if name == 'expiration' else name for name in options['fields'])}) for title, options in AccessAttemptAdmin.fieldsets)

    @admin.display(description='Expiration')
    def attempt_expiration(self, obj):
        return self.expiration(obj)


@admin.register(AccessLog)
class LoginAccessAdmin(LoginSecurityAdminMixin, AccessLogAdmin, ImportExportModelAdmin):
    pass


@admin.register(AccessFailureLog)
class LoginFailureAdmin(LoginSecurityAdminMixin, AccessFailureLogAdmin, ImportExportModelAdmin):
    pass


for model in apps.get_app_config("sanjilas").get_models():
    if not admin.site.is_registered(model):
        admin.site.register(model, ImportExportModelAdmin)

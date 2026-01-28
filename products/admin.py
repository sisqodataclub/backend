"""
Complete E-Commerce Admin Configuration for Multi-Tenant SaaS
Super Admin can see ALL data across ALL tenants using .all_objects
"""
from django.contrib import admin, messages
from django.db.models import Count, Avg
from django.utils.html import format_html
from django.utils import timezone
from django.urls import reverse
from .models import Product, ProductVariant, ProductImage, Review, Discount


# ============================================================================
# 1. Inline Models (Edit inside Product page)
# ============================================================================

class ProductImageInline(admin.TabularInline):
    """Inline for managing product images/gallery"""
    model = ProductImage
    extra = 1
    max_num = 20
    fields = ['image_preview', 'image_url', 'alt_text', 'is_primary', 'position']
    readonly_fields = ['image_preview']
    ordering = ['position']
    classes = ['collapse']
    verbose_name = "Product Image"
    verbose_name_plural = "Product Images (Gallery)"
    
    # ✅ Use all_objects to ensure data loads regardless of tenant context
    def get_queryset(self, request):
        return self.model.all_objects.all()

    def image_preview(self, obj):
        if obj.image_url:
            return format_html('<img src="{}" style="height: 40px; border-radius: 4px;" />', obj.image_url)
        return ""


class ProductVariantInline(admin.TabularInline):
    """Inline for managing product variants"""
    model = ProductVariant
    extra = 0
    fields = [
        'option1_value', 'option2_value',
        'sku', 'price', 'stock', 'is_active'
    ]
    show_change_link = True
    ordering = ['position']
    verbose_name = "Product Variant"
    verbose_name_plural = "Product Variants (Size/Color Options)"

    # ✅ Use all_objects to ensure data loads regardless of tenant context
    def get_queryset(self, request):
        return self.model.all_objects.all()


# ============================================================================
# 2. Product Admin - Main Model
# ============================================================================

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Admin interface for Products with multi-tenant support"""
    
    # List View
    list_display = [
        'product_image',
        'name',
        'tenant_link',
        'category',
        'price_display',
        'stock_status',
        'status_badge',
        'variant_count_display'
    ]
    list_display_links = ['product_image', 'name']
    list_filter = [
        'tenant',
        'is_active',
        'category',
        'track_inventory',
        'created_at'
    ]
    search_fields = [
        'name', 'sku', 'tenant__name', 'tenant__domain'
    ]
    list_per_page = 50
    list_select_related = ['tenant']
    actions = [
        'activate_products',
        'deactivate_products',
        'duplicate_products'
    ]
    date_hierarchy = 'created_at'
    save_on_top = True
    
    # Detail View
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = [
        'tenant', 'created_at', 'updated_at', 
        'view_count', 'total_sales', 'average_rating'
    ]
    inlines = [ProductImageInline, ProductVariantInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'tenant', 'name', 'slug', 'short_description', 'description'
            )
        }),
        ('Pricing', {
            'fields': (
                'price', 'cost_price', 'compare_at_price',
                'discount_type', 'discount_value', 
                'discount_start_date', 'discount_end_date'
            )
        }),
        ('Inventory', {
            'fields': (
                'sku', 'barcode', 'stock', 'track_inventory',
                'allow_backorders', 'low_stock_threshold'
            )
        }),
        ('Classification', {
            'fields': ('category', 'brand', 'tags')
        }),
        ('Media', {
            'fields': ('image_url', 'video_url'),
            'description': 'Main product image. Use gallery below for additional images.'
        }),
        ('Status', {
            'fields': (
                'is_active', 'is_featured', 'is_digital',
                'requires_shipping', 'is_taxable', 'has_variants'
            )
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description'),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': ('view_count', 'total_sales', 'average_rating', 'review_count'),
            'classes': ('collapse',)
        }),
    )
    
    # ✅ CRITICAL: Use all_objects to see ALL products across ALL tenants
    def get_queryset(self, request):
        qs = self.model.objects.all().select_related('tenant')
        # Add annotations for performance
        return qs.annotate(
            variant_count=Count('variants', distinct=True),
        )
    
    # Custom Display Methods
    def product_image(self, obj):
        if obj.image_url:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 4px;" />',
                obj.image_url
            )
        return "🖼️"
    product_image.short_description = "Image"
    
    def tenant_link(self, obj):
        url = reverse('admin:core_tenant_change', args=[obj.tenant.id])
        return format_html('<a href="{}">{}</a>', url, obj.tenant.name)
    tenant_link.short_description = "Tenant"
    tenant_link.admin_order_field = 'tenant__name'
    
    def price_display(self, obj):
        if obj.compare_at_price and obj.compare_at_price > obj.price:
            return format_html(
                '<s style="color: #999;">${}</s> <strong>${}</strong>',
                obj.compare_at_price, obj.price
            )
        return f"${obj.price}"
    price_display.short_description = "Price"
    
    def stock_status(self, obj):
        if not obj.track_inventory:
            return format_html('<span style="color: #3498db;">∞ Unlimited</span>')
        
        if obj.stock <= 0:
            if obj.allow_backorders:
                return format_html('<span style="color: #e67e22;">⚠ Backorder</span>')
            return format_html('<span style="color: #e74c3c; font-weight: bold;">✗ Out of Stock</span>')
        elif obj.stock <= obj.low_stock_threshold:
            return format_html('<span style="color: #e67e22;">Low ({})</span>', obj.stock)
        else:
            return format_html('<span style="color: #27ae60;">✓ {}</span>', obj.stock)
    stock_status.short_description = "Stock"
    
    def status_badge(self, obj):
        if obj.is_active:
            return format_html('<span style="background: #27ae60; color: white; padding: 2px 6px; border-radius: 3px;">Active</span>')
        return format_html('<span style="background: #95a5a6; color: white; padding: 2px 6px; border-radius: 3px;">Inactive</span>')
    status_badge.short_description = "Status"
    
    def variant_count_display(self, obj):
        return obj.variant_count
    variant_count_display.short_description = "Variants"
    variant_count_display.admin_order_field = 'variant_count'
    
    # Actions
    def activate_products(self, request, queryset):
        updated = queryset.update(is_active=True, published_at=timezone.now())
        self.message_user(request, f'{updated} products activated.')
    
    def deactivate_products(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} products deactivated.')
    
    def duplicate_products(self, request, queryset):
        duplicated = 0
        for product in queryset:
            try:
                new_product = product
                new_product.pk = None
                new_product.sku = f"{product.sku}-COPY" if product.sku else ""
                new_product.slug = f"{product.slug}-copy"
                new_product.name = f"{product.name} (Copy)"
                new_product.total_sales = 0
                new_product.view_count = 0
                new_product.save()
                duplicated += 1
            except Exception as e:
                self.message_user(request, f"Error duplicating {product.name}: {e}", messages.ERROR)
        
        self.message_user(request, f'{duplicated} products duplicated successfully.')
    
    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        product = form.instance
        # Auto-update has_variants flag based on inline variants
        if product.variants.exists() != product.has_variants:
            product.has_variants = product.variants.exists()
            product.save(update_fields=['has_variants'])


# ============================================================================
# 3. Product Variant Admin
# ============================================================================

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = [
        'variant_display', 'product_link', 'tenant', 
        'sku', 'price_display', 'stock_status', 'is_active'
    ]
    list_filter = ['tenant', 'is_active', 'created_at']
    search_fields = ['sku', 'product__name', 'tenant__name', 'option1_value']
    list_select_related = ['product', 'tenant']
    readonly_fields = ['created_at', 'updated_at']
    
    # ✅ CRITICAL: Use all_objects to see ALL variants
    def get_queryset(self, request):
        return self.model.all_objects.all().select_related('product', 'tenant')
    
    def variant_display(self, obj):
        return obj.display_name
    variant_display.short_description = "Variant"
    
    def product_link(self, obj):
        url = reverse('admin:products_product_change', args=[obj.product.id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)
    product_link.short_description = "Product"
    
    def price_display(self, obj):
        if obj.price: return f"${obj.price}"
        return format_html('<span style="color: #7f8c8d;">(Parent)</span>')
    price_display.short_description = "Price"
    
    def stock_status(self, obj):
        if obj.stock <= 0:
            return format_html('<span style="color: #e74c3c;">✗ 0</span>')
        return format_html('<span style="color: #27ae60;">✓ {}</span>', obj.stock)
    stock_status.short_description = "Stock"


# ============================================================================
# 4. Review Admin
# ============================================================================

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = [
        'rating_stars', 'product_link', 'customer_name', 
        'tenant', 'is_approved_badge', 'created_at'
    ]
    list_filter = ['tenant', 'rating', 'is_approved', 'created_at']
    search_fields = ['customer_name', 'content', 'product__name']
    actions = ['approve_reviews', 'unapprove_reviews']
    readonly_fields = ['created_at', 'updated_at']
    
    # ✅ CRITICAL: Use all_objects
    def get_queryset(self, request):
        return self.model.all_objects.all().select_related('product', 'tenant')
    
    def rating_stars(self, obj):
        return format_html('<span style="color: #f39c12;">{}</span>', '★' * obj.rating)
    rating_stars.short_description = "Rating"
    
    def product_link(self, obj):
        url = reverse('admin:products_product_change', args=[obj.product.id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)
    product_link.short_description = "Product"
    
    def is_approved_badge(self, obj):
        if obj.is_approved:
            return format_html('<span style="color: #27ae60;">Approved</span>')
        return format_html('<span style="color: #e74c3c;">Pending</span>')
    is_approved_badge.short_description = "Status"
    
    def approve_reviews(self, request, queryset):
        queryset.update(is_approved=True)
        # Update product ratings for selected
        for review in queryset: review.product.update_rating(review.rating)
        self.message_user(request, "Reviews approved.")
    
    def unapprove_reviews(self, request, queryset):
        queryset.update(is_approved=False)
        self.message_user(request, "Reviews unapproved.")


# ============================================================================
# 5. Discount Admin
# ============================================================================

@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'tenant_link', 'discount_type', 'value_display',
        'times_used', 'is_active', 'end_date'
    ]
    list_filter = ['tenant', 'discount_type', 'is_active']
    search_fields = ['code', 'tenant__name']
    filter_horizontal = ['products']
    
    # ✅ CRITICAL: Use all_objects
    def get_queryset(self, request):
        return self.model.all_objects.all().select_related('tenant')
    
    def tenant_link(self, obj):
        url = reverse('admin:core_tenant_change', args=[obj.tenant.id])
        return format_html('<a href="{}">{}</a>', url, obj.tenant.name)
    tenant_link.short_description = "Tenant"
    
    def value_display(self, obj):
        if obj.discount_type == 'percentage': return f"{obj.discount_value}%"
        if obj.discount_type == 'fixed_amount': return f"${obj.discount_value}"
        return obj.discount_type
    value_display.short_description = "Value"
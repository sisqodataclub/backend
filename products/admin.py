"""
Complete E-Commerce Admin Configuration
With Inline Editing for Images and Variants
"""
from django.contrib import admin
from .models import Product, ProductVariant, ProductImage, Review, Discount

# ==========================================
# 1. Inlines (Edit these INSIDE the Product page)
# ==========================================

class ProductImageInline(admin.TabularInline):
    """
    Add/Edit product images directly inside Product page
    """
    model = ProductImage
    extra = 1  # Show 1 empty slot by default
    fields = ['image_url', 'alt_text', 'is_primary', 'position']
    ordering = ['position']


class ProductVariantInline(admin.TabularInline):
    """
    Add/Edit product variants (size/color) directly inside Product page
    """
    model = ProductVariant
    extra = 0  # Don't show empty slots (they clutter the page)
    fields = ['option1_value', 'option2_value', 'sku', 'price', 'stock', 'is_active']
    show_change_link = True  # Button to edit full details of variant
    ordering = ['position']


# ==========================================
# 2. Main Product Admin
# ==========================================

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """
    Main Product Admin with Inline Editing
    """
    list_display = [
        'name', 'tenant', 'sku', 'price', 'final_price', 
        'stock', 'is_active', 'is_featured', 'category'
    ]
    list_filter = [
        'tenant', 'is_active', 'is_featured', 'category', 
        'brand', 'is_digital', 'track_inventory'
    ]
    search_fields = ['name', 'sku', 'description', 'tags']
    prepopulated_fields = {'slug': ('name',)}
    
    # ⚡ INLINES - Edit Images & Variants inside Product page!
    inlines = [ProductImageInline, ProductVariantInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('tenant', 'name', 'slug', 'short_description', 'description')
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
        ('Physical Properties', {
            'fields': ('weight', 'length', 'width', 'height'),
            'classes': ('collapse',)
        }),
        ('Media', {
            'fields': ('image_url', 'video_url'),
            'description': 'Main product image. Additional images can be added below in the Images section.'
        }),
        ('Status & Features', {
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
            'fields': ('average_rating', 'review_count', 'total_sales', 'view_count'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['average_rating', 'review_count', 'total_sales', 'view_count']
    
    # Save the product first, then save related objects
    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # Automatically set has_variants if variants exist
        if form.instance.variants.exists() and not form.instance.has_variants:
            form.instance.has_variants = True
            form.instance.save(update_fields=['has_variants'])


# ==========================================
# 3. Variant Admin (Standalone)
# ==========================================

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    """
    Standalone Variant Admin (can also be edited inline on Product page)
    """
    list_display = [
        'product', 'display_name', 'sku', 'price', 'stock', 'is_active'
    ]
    list_filter = ['tenant', 'is_active', 'product']
    search_fields = ['sku', 'option1_value', 'option2_value', 'option3_value', 'product__name']
    list_editable = ['is_active']
    
    fieldsets = (
        ('Product', {
            'fields': ('tenant', 'product')
        }),
        ('Variant Options', {
            'fields': (
                ('option1_name', 'option1_value'),
                ('option2_name', 'option2_value'),
                ('option3_name', 'option3_value'),
            )
        }),
        ('Pricing', {
            'fields': ('price', 'compare_at_price')
        }),
        ('Inventory', {
            'fields': ('sku', 'barcode', 'stock', 'weight')
        }),
        ('Media & Status', {
            'fields': ('image_url', 'is_active', 'position')
        }),
    )


# ==========================================
# 4. Image Admin (Standalone)
# ==========================================

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    """
    Standalone Image Admin (can also be edited inline on Product page)
    """
    list_display = ['product', 'position', 'is_primary', 'alt_text', 'image_preview']
    list_filter = ['tenant', 'is_primary']
    list_editable = ['position', 'is_primary']
    search_fields = ['product__name', 'alt_text']
    
    def image_preview(self, obj):
        """Show small image preview in admin list"""
        if obj.image_url:
            return f'<img src="{obj.image_url}" style="max-height:50px; max-width:100px;" />'
        return 'No image'
    image_preview.allow_tags = True
    image_preview.short_description = 'Preview'


# ==========================================
# 5. Review Admin
# ==========================================

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    """
    Review moderation and management
    """
    list_display = [
        'product', 'customer_name', 'rating', 
        'is_approved', 'is_verified_purchase', 'created_at'
    ]
    list_filter = [
        'tenant', 'rating', 'is_approved', 
        'is_verified_purchase', 'created_at'
    ]
    search_fields = ['customer_name', 'customer_email', 'content', 'product__name']
    list_editable = ['is_approved']
    readonly_fields = ['helpful_count', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Product & Customer', {
            'fields': ('tenant', 'product', 'customer_name', 'customer_email')
        }),
        ('Review Content', {
            'fields': ('rating', 'title', 'content', 'image_url')
        }),
        ('Moderation', {
            'fields': ('is_approved', 'is_verified_purchase')
        }),
        ('Engagement', {
            'fields': ('helpful_count',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['approve_reviews', 'unapprove_reviews']
    
    def approve_reviews(self, request, queryset):
        """Bulk approve selected reviews"""
        updated = queryset.update(is_approved=True)
        self.message_user(request, f'{updated} review(s) approved.')
    approve_reviews.short_description = 'Approve selected reviews'
    
    def unapprove_reviews(self, request, queryset):
        """Bulk unapprove selected reviews"""
        updated = queryset.update(is_approved=False)
        self.message_user(request, f'{updated} review(s) unapproved.')
    unapprove_reviews.short_description = 'Unapprove selected reviews'


# ==========================================
# 6. Discount Admin
# ==========================================

@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    """
    Coupon and discount code management
    """
    list_display = [
        'code', 'tenant', 'discount_type', 'discount_value',
        'applies_to', 'times_used', 'is_active', 'is_valid_now', 'start_date', 'end_date'
    ]
    list_filter = [
        'tenant', 'discount_type', 'applies_to', 
        'is_active', 'start_date', 'end_date'
    ]
    search_fields = ['code', 'description']
    readonly_fields = ['times_used', 'created_at', 'updated_at']
    filter_horizontal = ['products']
    date_hierarchy = 'start_date'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('tenant', 'code', 'description')
        }),
        ('Discount Configuration', {
            'fields': (
                'discount_type', 'discount_value',
                'applies_to', 'products', 'categories'
            )
        }),
        ('Requirements & Limits', {
            'fields': (
                'minimum_purchase', 'usage_limit',
                'usage_limit_per_customer', 'times_used'
            )
        }),
        ('Schedule', {
            'fields': ('start_date', 'end_date', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def is_valid_now(self, obj):
        """Show if discount is currently valid"""
        return obj.is_valid
    is_valid_now.boolean = True
    is_valid_now.short_description = 'Valid Now?'
    
    actions = ['activate_discounts', 'deactivate_discounts']
    
    def activate_discounts(self, request, queryset):
        """Bulk activate selected discounts"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} discount(s) activated.')
    activate_discounts.short_description = 'Activate selected discounts'
    
    def deactivate_discounts(self, request, queryset):
        """Bulk deactivate selected discounts"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} discount(s) deactivated.')
    deactivate_discounts.short_description = 'Deactivate selected discounts'

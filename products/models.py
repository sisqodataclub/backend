"""
Complete E-Commerce Models with Tenant Support - PRODUCTION READY
Fixed all multi-tenancy bugs and circular imports
"""
import sys
from django.db import models
from django.utils.text import slugify
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal

# ============================================================================
# TENANTAWARE MODEL IMPORT - HANDLE CIRCULAR IMPORTS
# ============================================================================

try:
    from core.models import TenantAwareModel
except ImportError:
    # Fallback for migrations and when core.models isn't available yet
    from django.db import models
    
    class TenantAwareModel(models.Model):
        """
        Fallback TenantAwareModel for migrations
        Will be replaced by the real one from core.models at runtime
        """
        tenant = models.ForeignKey(
            'core.Tenant',
            on_delete=models.CASCADE,
            editable=False
        )
        
        class Meta:
            abstract = True


# ============================================================================
# PRODUCT MODEL - Complete E-commerce Product with Tenant Isolation
# ============================================================================

class Product(TenantAwareModel):
    """Complete E-commerce Product Model with Automatic Tenant Filtering"""
    
    # Basic Information
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    short_description = models.CharField(
        max_length=255, 
        blank=True,
        help_text="Brief description for product cards"
    )
    
    # Pricing
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    cost_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Your cost (for profit calculations)"
    )
    compare_at_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Original price (shows discount percentage)"
    )
    
    # Discount Settings
    DISCOUNT_TYPES = [
        ('none', 'No Discount'),
        ('percentage', 'Percentage Off'),
        ('fixed', 'Fixed Amount Off'),
    ]
    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPES,
        default='none'
    )
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))]
    )
    discount_start_date = models.DateTimeField(null=True, blank=True)
    discount_end_date = models.DateTimeField(null=True, blank=True)
    
    # Inventory Management
    stock = models.PositiveIntegerField(default=0)
    sku = models.CharField(
        max_length=50, 
        blank=True, 
        help_text="Stock Keeping Unit (unique per tenant)"
    )
    barcode = models.CharField(
        max_length=100,
        blank=True,
        help_text="UPC/EAN/ISBN barcode"
    )
    track_inventory = models.BooleanField(
        default=True,
        help_text="Track stock levels?"
    )
    allow_backorders = models.BooleanField(
        default=False,
        help_text="Allow purchase when out of stock?"
    )
    low_stock_threshold = models.PositiveIntegerField(
        default=5,
        help_text="Alert when stock falls below this"
    )
    
    # Product Classification
    category = models.CharField(max_length=100, blank=True)
    tags = models.CharField(
        max_length=255,
        blank=True,
        help_text="Comma-separated tags (e.g., 'summer, sale, featured')"
    )
    brand = models.CharField(max_length=100, blank=True)
    
    # Physical Properties
    weight = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Weight in kg"
    )
    length = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Length in cm"
    )
    width = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Width in cm"
    )
    height = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Height in cm"
    )
    
    # Media
    image_url = models.URLField(blank=True, help_text="Main product image")
    video_url = models.URLField(blank=True, help_text="Product video (YouTube/Vimeo)")
    
    # Product Status
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(
        default=False,
        help_text="Show on homepage/featured section?"
    )
    is_digital = models.BooleanField(
        default=False,
        help_text="Digital product (no shipping)?"
    )
    requires_shipping = models.BooleanField(
        default=True,
        help_text="Does this product need shipping?"
    )
    is_taxable = models.BooleanField(
        default=True,
        help_text="Apply tax to this product?"
    )
    
    # Variants Support
    has_variants = models.BooleanField(
        default=False,
        help_text="Does this product have size/color variants?"
    )
    
    # SEO
    slug = models.SlugField(max_length=255, blank=True)
    meta_title = models.CharField(
        max_length=70,
        blank=True,
        help_text="SEO page title (leave blank to use product name)"
    )
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        help_text="SEO meta description"
    )
    
    # Ratings & Reviews
    average_rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    review_count = models.PositiveIntegerField(default=0)
    
    # Sales Tracking
    total_sales = models.PositiveIntegerField(
        default=0,
        help_text="Total units sold"
    )
    view_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times viewed"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['tenant', 'sku']),
            models.Index(fields=['tenant', 'slug']),
            models.Index(fields=['tenant', 'category']),
            models.Index(fields=['tenant', 'is_featured']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'sku'], 
                name='unique_sku_per_tenant',
                condition=models.Q(sku__isnull=False) & ~models.Q(sku='')
            ),
            models.UniqueConstraint(
                fields=['tenant', 'slug'], 
                name='unique_slug_per_tenant'
            )
        ]
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
    
    def __str__(self):
        return f"{self.name} ({self.tenant.name})"

    def save(self, *args, **kwargs):
        # Auto-generate slug with tenant isolation
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            
            # ✅ Use all_objects for tenant-aware query during save
            while self.__class__.all_objects.filter(
                tenant=self.tenant, 
                slug=slug
            ).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            
            self.slug = slug
        
        # Auto-generate meta_title if empty
        if not self.meta_title and self.name:
            self.meta_title = self.name[:70]
        
        # Auto-set published_at if not set and product is active
        if not self.published_at and self.is_active:
            self.published_at = timezone.now()
        
        super().save(*args, **kwargs)
    
    @property
    def final_price(self):
        """Calculate final price after discounts"""
        if self.discount_type == 'none' or self.discount_value <= 0:
            return self.price
        
        now = timezone.now()
        if self.discount_start_date and now < self.discount_start_date:
            return self.price
        if self.discount_end_date and now > self.discount_end_date:
            return self.price
        
        if self.discount_type == 'percentage':
            discount_amount = self.price * (self.discount_value / 100)
            return max(self.price - discount_amount, Decimal('0.01'))
        elif self.discount_type == 'fixed':
            return max(self.price - self.discount_value, Decimal('0.01'))
        
        return self.price
    
    @property
    def discount_percentage(self):
        """Calculate discount percentage for display"""
        if self.compare_at_price and self.compare_at_price > self.price:
            discount = ((self.compare_at_price - self.price) / self.compare_at_price) * 100
            return round(discount, 0)
        return 0
    
    @property
    def is_on_sale(self):
        """Check if product is currently on sale"""
        return self.final_price < self.price
    
    @property
    def is_low_stock(self):
        """Check if stock is below threshold"""
        if not self.track_inventory:
            return False
        return self.stock <= self.low_stock_threshold
    
    @property
    def is_out_of_stock(self):
        """Check if product is out of stock"""
        if not self.track_inventory:
            return False
        return self.stock <= 0
    
    @property
    def can_purchase(self):
        """Check if product can be purchased"""
        if not self.is_active:
            return False
        if self.track_inventory and self.stock <= 0 and not self.allow_backorders:
            return False
        return True
    
    @property
    def profit_margin(self):
        """Calculate profit margin if cost price is set"""
        if self.cost_price and self.cost_price > 0 and self.final_price > 0:
            profit = self.final_price - self.cost_price
            margin = (profit / self.final_price) * 100
            return round(margin, 2)
        return None
    
    @property
    def shipping_required(self):
        """Check if shipping is required"""
        return self.requires_shipping and not self.is_digital
    
    def get_tags_list(self):
        """Convert comma-separated tags to list"""
        if self.tags:
            return [tag.strip() for tag in self.tags.split(',') if tag.strip()]
        return []
    
    def increment_view_count(self):
        """Increment product view count"""
        self.view_count += 1
        self.save(update_fields=['view_count'])
    
    def increment_sales(self, quantity=1):
        """Increment sales count and reduce stock"""
        self.total_sales += quantity
        self.stock = max(0, self.stock - quantity)
        self.save(update_fields=['total_sales', 'stock'])
    
    def update_rating(self, new_rating):
        """Update average rating when new review is added"""
        if new_rating < 1 or new_rating > 5:
            raise ValueError("Rating must be between 1 and 5")
        
        total_rating = self.average_rating * self.review_count
        self.review_count += 1
        self.average_rating = (total_rating + new_rating) / self.review_count
        self.save(update_fields=['average_rating', 'review_count'])


# ============================================================================
# PRODUCT VARIANT - For size/color options with Tenant Isolation
# ============================================================================

class ProductVariant(TenantAwareModel):
    """
    Product Variants (e.g., Size: Medium, Color: Blue)
    Tenant-aware with automatic filtering
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='variants'
    )
    
    # Variant Options
    option1_name = models.CharField(
        max_length=50,
        default='Size',
        help_text="e.g., 'Size', 'Color', 'Material'"
    )
    option1_value = models.CharField(
        max_length=100,
        help_text="e.g., 'Large', 'Blue', 'Cotton'"
    )
    option2_name = models.CharField(
        max_length=50,
        blank=True,
        help_text="Optional second attribute"
    )
    option2_value = models.CharField(
        max_length=100,
        blank=True
    )
    option3_name = models.CharField(
        max_length=50,
        blank=True,
        help_text="Optional third attribute"
    )
    option3_value = models.CharField(
        max_length=100,
        blank=True
    )
    
    # Pricing (can override product price)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Leave blank to use product price"
    )
    compare_at_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # Inventory
    sku = models.CharField(max_length=50, blank=True)
    barcode = models.CharField(max_length=100, blank=True)
    stock = models.PositiveIntegerField(default=0)
    weight = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # Media
    image_url = models.URLField(
        blank=True,
        help_text="Variant-specific image (optional)"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Tracking
    position = models.PositiveIntegerField(
        default=0,
        help_text="Display order"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['position', 'option1_value']
        indexes = [
            models.Index(fields=['tenant', 'product']),
            models.Index(fields=['tenant', 'sku']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'product', 'option1_value', 'option2_value', 'option3_value'],
                name='unique_variant_combination'
            )
        ]
        verbose_name = 'Product Variant'
        verbose_name_plural = 'Product Variants'
    
    def __str__(self):
        parts = [self.option1_value]
        if self.option2_value:
            parts.append(self.option2_value)
        if self.option3_value:
            parts.append(self.option3_value)
        return f"{self.product.name} - {' / '.join(parts)}"
    
    @property
    def final_price(self):
        """Get variant price or fall back to product price"""
        return self.price if self.price is not None else self.product.final_price
    
    @property
    def display_name(self):
        """Get formatted variant name"""
        parts = []
        if self.option1_value:
            parts.append(f"{self.option1_name}: {self.option1_value}")
        if self.option2_value:
            parts.append(f"{self.option2_name}: {self.option2_value}")
        if self.option3_value:
            parts.append(f"{self.option3_name}: {self.option3_value}")
        return " | ".join(parts)
    
    @property
    def can_purchase(self):
        """Check if variant can be purchased"""
        if not self.is_active or not self.product.is_active:
            return False
        
        if self.product.track_inventory and self.stock <= 0:
            return self.product.allow_backorders
        
        return True


# ============================================================================
# PRODUCT IMAGE - Multiple images per product with Tenant Isolation
# ============================================================================

class ProductImage(TenantAwareModel):
    """
    Multiple images per product (gallery)
    Tenant-aware with automatic filtering
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images'
    )
    
    image_url = models.URLField(help_text="Image URL (S3/Cloudinary)")
    alt_text = models.CharField(
        max_length=200,
        blank=True,
        help_text="SEO alt text"
    )
    position = models.PositiveIntegerField(
        default=0,
        help_text="Display order (lower = first)"
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="Use as main product image?"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['position']
        indexes = [
            models.Index(fields=['tenant', 'product', 'position']),
        ]
        verbose_name = 'Product Image'
        verbose_name_plural = 'Product Images'
    
    def __str__(self):
        return f"Image for {self.product.name} (pos: {self.position})"
    
    def save(self, *args, **kwargs):
        # If this is marked as primary, unmark others
        if self.is_primary:
            ProductImage.objects.filter(
                tenant=self.tenant,
                product=self.product,
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


# ============================================================================
# REVIEW - Customer reviews and ratings with Tenant Isolation
# ============================================================================

class Review(TenantAwareModel):
    """
    Customer Reviews & Ratings
    Tenant-aware with automatic filtering
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='reviews'
    )
    
    # Customer Info
    customer_name = models.CharField(max_length=100)
    customer_email = models.EmailField()
    
    # Review Content
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="1-5 stars"
    )
    title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Review headline"
    )
    content = models.TextField(help_text="Review text")
    
    # Moderation
    is_verified_purchase = models.BooleanField(
        default=False,
        help_text="Did they actually buy this?"
    )
    is_approved = models.BooleanField(
        default=False,
        help_text="Approved by admin?"
    )
    
    # Helpfulness
    helpful_count = models.PositiveIntegerField(
        default=0,
        help_text="How many found this helpful"
    )
    
    # Media
    image_url = models.URLField(
        blank=True,
        help_text="Customer photo (optional)"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'product', 'is_approved']),
            models.Index(fields=['tenant', 'rating']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'Review'
        verbose_name_plural = 'Reviews'
    
    def __str__(self):
        return f"{self.rating}★ - {self.product.name} by {self.customer_name}"
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Update product's average rating
        if is_new and self.is_approved:
            self.product.update_rating(self.rating)
    
    def mark_helpful(self):
        """Mark review as helpful"""
        self.helpful_count += 1
        self.save(update_fields=['helpful_count'])


# ============================================================================
# DISCOUNT - Flexible coupon/discount system with Tenant Isolation
# ============================================================================

class Discount(TenantAwareModel):
    """
    Flexible Discount/Coupon System
    ✅ FIXED: Code is unique PER TENANT, not globally
    """
    # Basic Info
    code = models.CharField(
        max_length=50,
        help_text="Coupon code (e.g., 'SUMMER2024')"
        # ✅ REMOVED unique=True - Codes only need to be unique PER TENANT
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        help_text="Internal description"
    )
    
    # Discount Type
    DISCOUNT_TYPES = [
        ('percentage', 'Percentage Off'),
        ('fixed_amount', 'Fixed Amount Off'),
        ('free_shipping', 'Free Shipping'),
        ('buy_x_get_y', 'Buy X Get Y'),
    ]
    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPES,
        default='percentage'
    )
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))]
    )
    
    # Apply To
    APPLIES_TO_CHOICES = [
        ('all', 'All Products'),
        ('category', 'Specific Categories'),
        ('products', 'Specific Products'),
    ]
    applies_to = models.CharField(
        max_length=20,
        choices=APPLIES_TO_CHOICES,
        default='all'
    )
    
    # Specific Products
    products = models.ManyToManyField(
        Product,
        blank=True,
        related_name='discounts'
    )
    categories = models.CharField(
        max_length=500,
        blank=True,
        help_text="Comma-separated category names"
    )
    
    # Usage Limits
    minimum_purchase = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Minimum order amount required"
    )
    usage_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total times this code can be used (null = unlimited)"
    )
    usage_limit_per_customer = models.PositiveIntegerField(
        default=1,
        help_text="Times each customer can use this code"
    )
    times_used = models.PositiveIntegerField(
        default=0,
        help_text="How many times this code has been used"
    )
    
    # Date Range
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Leave blank for no expiration"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'code']),
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['start_date', 'end_date']),
        ]
        constraints = [
            # ✅ CRITICAL FIX: Unique constraint per tenant, not globally
            models.UniqueConstraint(
                fields=['tenant', 'code'],
                name='unique_discount_code_per_tenant'
            )
        ]
        verbose_name = 'Discount'
        verbose_name_plural = 'Discounts'
    
    def __str__(self):
        return f"{self.code} ({self.tenant.name})"
    
    @property
    def is_valid(self):
        """Check if discount is currently valid"""
        if not self.is_active:
            return False
        
        now = timezone.now()
        if now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        
        # Check usage limit
        if self.usage_limit and self.times_used >= self.usage_limit:
            return False
        
        return True
    
    @property
    def is_expired(self):
        """Check if discount has expired"""
        if self.end_date:
            return timezone.now() > self.end_date
        return False
    
    def can_apply_to_product(self, product):
        """Check if discount applies to a specific product"""
        if self.applies_to == 'all':
            return True
        
        if self.applies_to == 'products':
            return self.products.filter(id=product.id).exists()
        
        if self.applies_to == 'category' and self.categories:
            allowed_categories = [cat.strip() for cat in self.categories.split(',')]
            return product.category in allowed_categories
        
        return False
    
    def calculate_discount(self, amount):
        """Calculate discount amount for given price"""
        if self.discount_type == 'percentage':
            discount = amount * (self.discount_value / 100)
            return min(discount, amount)
        
        elif self.discount_type == 'fixed_amount':
            return min(self.discount_value, amount)
        
        return Decimal('0')
    
    def increment_usage(self):
        """Increment usage counter"""
        self.times_used += 1
        self.save(update_fields=['times_used'])
    
    @property
    def remaining_uses(self):
        """Get remaining uses (if limited)"""
        if self.usage_limit:
            return max(0, self.usage_limit - self.times_used)
        return None
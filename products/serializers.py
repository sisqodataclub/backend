"""
Complete E-Commerce Serializers with Multi-Tenant Security
Automatically handles tenant assignment and filtering
"""
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from decimal import Decimal
from .models import Product, ProductVariant, ProductImage, Review, Discount
from core.serializers import TenantAwareSerializer  # ✅ Use base tenant-aware serializer


# ============================================================================
# PRODUCT IMAGE SERIALIZER
# ============================================================================

class ProductImageSerializer(TenantAwareSerializer):
    """Serializer for product images with tenant auto-assignment"""
    
    class Meta:
        model = ProductImage
        exclude = ['tenant']
        read_only_fields = ['created_at']
    
    def validate_product(self, value):
        """Ensure product belongs to current tenant"""
        request = self.context.get('request')
        if request and hasattr(request, 'tenant'):
            if value.tenant_id != request.tenant.id:
                raise ValidationError("Product does not belong to your tenant.")
        return value


# ============================================================================
# PRODUCT VARIANT SERIALIZER
# ============================================================================

class ProductVariantSerializer(TenantAwareSerializer):
    """Serializer for product variants with tenant auto-assignment"""
    final_price = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        read_only=True
    )
    display_name = serializers.CharField(read_only=True)
    can_purchase = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = ProductVariant
        exclude = ['tenant']
        read_only_fields = ['created_at', 'updated_at']
    
    def validate_product(self, value):
        """Ensure product belongs to current tenant"""
        request = self.context.get('request')
        if request and hasattr(request, 'tenant'):
            if value.tenant_id != request.tenant.id:
                raise ValidationError("Product does not belong to your tenant.")
        return value


# ============================================================================
# REVIEW SERIALIZER
# ============================================================================

class ReviewSerializer(TenantAwareSerializer):
    """Serializer for reviews with tenant auto-assignment and security"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = Review
        exclude = ['tenant', 'is_verified_purchase']
        read_only_fields = [
            'helpful_count', 
            'is_approved', 
            'created_at', 
            'updated_at'
        ]
    
    def validate(self, data):
        """Validate review data"""
        request = self.context.get('request')
        
        # Ensure rating is valid
        rating = data.get('rating')
        if rating and (rating < 1 or rating > 5):
            raise ValidationError({"rating": "Rating must be between 1 and 5."})
        
        # Ensure product belongs to tenant
        product = data.get('product')
        if product and request and hasattr(request, 'tenant'):
            if product.tenant_id != request.tenant.id:
                raise ValidationError({"product": "Product does not belong to your tenant."})
        
        return data
    
    def create(self, validated_data):
        """Create review with auto-tenant assignment"""
        # Add tenant from request context
        request = self.context.get('request')
        if request and hasattr(request, 'tenant'):
            validated_data['tenant'] = request.tenant
        
        # Set is_approved to False by default (requires admin approval)
        validated_data['is_approved'] = False
        
        # Mark as verified purchase if customer email matches order history
        # (You'd implement this based on your order system)
        validated_data['is_verified_purchase'] = False
        
        return super().create(validated_data)


# ============================================================================
# PRODUCT LIST SERIALIZER (Lightweight for listings)
# ============================================================================

class ProductListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for product listings
    Tenant-filtered automatically by Product.objects manager
    """
    final_price = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        read_only=True
    )
    discount_percentage = serializers.IntegerField(read_only=True)
    is_on_sale = serializers.BooleanField(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    can_purchase = serializers.BooleanField(read_only=True)
    thumbnail = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'short_description', 'slug',
            'price', 'final_price', 'discount_percentage',
            'compare_at_price', 'thumbnail', 'image_url',
            'is_featured', 'is_on_sale', 'is_low_stock',
            'can_purchase', 'average_rating', 'review_count',
            'category', 'brand', 'stock', 'has_variants',
            'created_at'
        ]
        read_only_fields = ['created_at']
    
    def get_thumbnail(self, obj):
        """Get thumbnail URL or use image_url"""
        request = self.context.get('request')
        if request:
            # You could generate thumbnails here
            # For now, return the main image
            return obj.image_url
        return None
    
    def to_representation(self, instance):
        """Custom representation for performance"""
        data = super().to_representation(instance)
        
        # Add tenant context if needed
        request = self.context.get('request')
        if request and request.user.is_staff:
            data['tenant'] = instance.tenant.name
        
        return data


# ============================================================================
# PRODUCT DETAIL SERIALIZER (Full details with relationships)
# ============================================================================

class ProductDetailSerializer(TenantAwareSerializer):
    """
    Full product details with all relationships
    Automatically filters variants/images/reviews by tenant
    """
    # Computed fields
    final_price = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        read_only=True
    )
    discount_percentage = serializers.IntegerField(read_only=True)
    is_on_sale = serializers.BooleanField(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    is_out_of_stock = serializers.BooleanField(read_only=True)
    can_purchase = serializers.BooleanField(read_only=True)
    profit_margin = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        read_only=True,
        allow_null=True
    )
    shipping_required = serializers.BooleanField(read_only=True)
    tags_list = serializers.SerializerMethodField()
    
    # Related objects - filtered by tenant automatically
    variants = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    reviews = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        exclude = ['tenant', 'cost_price']  # Hide cost from public
        read_only_fields = [
            'average_rating', 
            'review_count', 
            'total_sales', 
            'view_count', 
            'created_at', 
            'updated_at',
            'published_at'
        ]
    
    def get_tags_list(self, obj):
        return obj.get_tags_list()
    
    def get_variants(self, obj):
        """Get variants filtered by current tenant"""
        variants = obj.variants.filter(is_active=True)
        serializer = ProductVariantSerializer(
            variants, 
            many=True,
            context=self.context
        )
        return serializer.data
    
    def get_images(self, obj):
        """Get images filtered by current tenant"""
        images = obj.images.all()
        serializer = ProductImageSerializer(
            images, 
            many=True,
            context=self.context
        )
        return serializer.data
    
    def get_reviews(self, obj):
        """Get approved reviews filtered by current tenant"""
        reviews = obj.reviews.filter(is_approved=True)
        serializer = ReviewSerializer(
            reviews, 
            many=True,
            context=self.context
        )
        return serializer.data
    
    def to_representation(self, instance):
        """Custom representation with tenant filtering"""
        data = super().to_representation(instance)
        
        # Add related counts
        data['variant_count'] = instance.variants.count()
        data['image_count'] = instance.images.count()
        data['approved_review_count'] = instance.reviews.filter(is_approved=True).count()
        
        # For admin users, include tenant info
        request = self.context.get('request')
        if request and request.user.is_staff:
            data['tenant'] = {
                'id': instance.tenant.id,
                'name': instance.tenant.name,
                'domain': instance.tenant.domain
            }
        
        return data


# ============================================================================
# DISCOUNT SERIALIZER
# ============================================================================

class DiscountSerializer(TenantAwareSerializer):
    """Serializer for discounts with tenant auto-assignment"""
    is_valid = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    remaining_uses = serializers.IntegerField(read_only=True, allow_null=True)
    
    # Related fields
    applicable_products = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Discount
        exclude = ['tenant']
        read_only_fields = ['times_used', 'created_at', 'updated_at']
    
    def get_applicable_products(self, obj):
        """Get list of applicable product IDs"""
        if obj.applies_to == 'products':
            return list(obj.products.values_list('id', flat=True))
        return []
    
    def get_product_count(self, obj):
        """Get count of applicable products"""
        if obj.applies_to == 'products':
            return obj.products.count()
        return None
    
    def validate_code(self, value):
        """Ensure discount code is unique within tenant"""
        request = self.context.get('request')
        if request and hasattr(request, 'tenant'):
            # Check if code already exists for this tenant
            existing = Discount.objects.filter(
                tenant=request.tenant,
                code__iexact=value
            )
            
            # If updating, exclude current instance
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise ValidationError("Discount code already exists for this tenant.")
        
        return value.upper()  # Store codes in uppercase
    
    def create(self, validated_data):
        """Create discount with tenant auto-assignment"""
        request = self.context.get('request')
        if request and hasattr(request, 'tenant'):
            validated_data['tenant'] = request.tenant
        
        # Uppercase the code
        validated_data['code'] = validated_data.get('code', '').upper()
        
        return super().create(validated_data)


# ============================================================================
# DISCOUNT VALIDATION SERIALIZER
# ============================================================================

class DiscountValidationSerializer(serializers.Serializer):
    """
    For validating discount codes at checkout
    Returns discount details if valid
    """
    code = serializers.CharField(max_length=50)
    cart_total = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        required=False,
        default=0,
        min_value=0
    )
    product_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
        help_text="List of product IDs in cart"
    )
    
    def validate(self, data):
        """Validate discount code"""
        request = self.context.get('request')
        code = data.get('code', '').upper()
        cart_total = data.get('cart_total', 0)
        product_ids = data.get('product_ids', [])
        
        if not request or not hasattr(request, 'tenant'):
            raise ValidationError("Tenant context required.")
        
        # Find discount for current tenant
        try:
            discount = Discount.objects.get(
                tenant=request.tenant,
                code=code,
                is_active=True
            )
        except Discount.DoesNotExist:
            raise ValidationError({"code": "Invalid discount code."})
        
        # Check if valid
        if not discount.is_valid:
            if discount.is_expired:
                raise ValidationError({"code": "Discount code has expired."})
            else:
                raise ValidationError({"code": "Discount code is not currently active."})
        
        # Check minimum purchase
        if cart_total < discount.minimum_purchase:
            raise ValidationError({
                "code": f"Minimum purchase of ${discount.minimum_purchase} required."
            })
        
        # Check if applies to products in cart
        if discount.applies_to != 'all' and product_ids:
            applicable = False
            
            if discount.applies_to == 'products':
                # Check if any product in cart is in discount products
                discount_product_ids = discount.products.values_list('id', flat=True)
                applicable = any(pid in discount_product_ids for pid in product_ids)
            
            elif discount.applies_to == 'category' and discount.categories:
                # You'd need to fetch products and check categories
                # For simplicity, we'll skip this check in serializer
                pass
            
            if not applicable:
                raise ValidationError({
                    "code": "Discount code does not apply to products in your cart."
                })
        
        # Return discount details if valid
        data['discount'] = discount
        data['discount_amount'] = discount.calculate_discount(cart_total)
        
        return data


# ============================================================================
# PRODUCT CREATE/UPDATE SERIALIZER
# ============================================================================

class ProductCreateUpdateSerializer(TenantAwareSerializer):
    """Serializer for creating/updating products with validation"""
    
    class Meta:
        model = Product
        exclude = ['tenant']
        read_only_fields = [
            'average_rating',
            'review_count',
            'total_sales',
            'view_count',
            'created_at',
            'updated_at',
            'published_at'
        ]
    
    def validate(self, data):
        """Validate product data"""
        # Ensure price is positive
        price = data.get('price')
        if price and price <= 0:
            raise ValidationError({"price": "Price must be greater than 0."})
        
        # Ensure compare_at_price > price if set
        compare_at_price = data.get('compare_at_price')
        if compare_at_price and price and compare_at_price <= price:
            raise ValidationError({
                "compare_at_price": "Compare at price must be greater than current price."
            })
        
        # Validate discount dates
        discount_start = data.get('discount_start_date')
        discount_end = data.get('discount_end_date')
        if discount_start and discount_end and discount_start >= discount_end:
            raise ValidationError({
                "discount_end_date": "Discount end date must be after start date."
            })
        
        return data
    
    def create(self, validated_data):
        """Create product with auto-slug generation"""
        request = self.context.get('request')
        if request and hasattr(request, 'tenant'):
            validated_data['tenant'] = request.tenant
        
        # Auto-set published_at if product is active
        if validated_data.get('is_active', False) and not validated_data.get('published_at'):
            from django.utils import timezone
            validated_data['published_at'] = timezone.now()
        
        return super().create(validated_data)


# ============================================================================
# REVIEW VOTE SERIALIZER
# ============================================================================

class ReviewVoteSerializer(serializers.Serializer):
    """Serializer for voting on reviews (helpful/not helpful)"""
    review_id = serializers.IntegerField()
    helpful = serializers.BooleanField(default=True)
    
    def validate(self, data):
        """Validate review vote"""
        review_id = data.get('review_id')
        
        try:
            review = Review.objects.get(id=review_id)
            request = self.context.get('request')
            
            # Ensure review belongs to current tenant
            if request and hasattr(request, 'tenant'):
                if review.tenant_id != request.tenant.id:
                    raise ValidationError({"review_id": "Review not found."})
            
            data['review'] = review
        except Review.DoesNotExist:
            raise ValidationError({"review_id": "Review not found."})
        
        return data
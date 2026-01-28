"""
Complete E-Commerce Serializers
All serializers for Product, Variant, Image, Review, Discount
"""
from rest_framework import serializers
from .models import Product, ProductVariant, ProductImage, Review, Discount


# ============================================================================
# PRODUCT IMAGE SERIALIZER
# ============================================================================

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        exclude = ['tenant']
        read_only_fields = ['created_at']


# ============================================================================
# PRODUCT VARIANT SERIALIZER
# ============================================================================

class ProductVariantSerializer(serializers.ModelSerializer):
    final_price = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        read_only=True
    )
    display_name = serializers.CharField(read_only=True)
    
    class Meta:
        model = ProductVariant
        exclude = ['tenant', 'product']
        read_only_fields = ['created_at', 'updated_at']


# ============================================================================
# REVIEW SERIALIZER
# ============================================================================

class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        exclude = ['tenant', 'product']
        read_only_fields = ['helpful_count', 'is_approved', 'is_verified_purchase', 'created_at', 'updated_at']


# ============================================================================
# PRODUCT LIST SERIALIZER (Lightweight for listings)
# ============================================================================

class ProductListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for product listings
    Fast performance - no related objects
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
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'short_description', 'slug',
            'price', 'final_price', 'discount_percentage',
            'compare_at_price', 'image_url', 
            'is_featured', 'is_on_sale', 'is_low_stock',
            'can_purchase', 'average_rating', 'review_count',
            'category', 'brand', 'stock', 'has_variants'
        ]


# ============================================================================
# PRODUCT DETAIL SERIALIZER (Full details with relationships)
# ============================================================================

class ProductDetailSerializer(serializers.ModelSerializer):
    """
    Full product details with all relationships
    Includes variants, images, and reviews
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
    tags_list = serializers.SerializerMethodField()
    
    # Related objects
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    
    class Meta:
        model = Product
        exclude = ['tenant', 'cost_price']  # Hide cost from public
        read_only_fields = ['average_rating', 'review_count', 'total_sales', 'view_count', 'created_at', 'updated_at']
    
    def get_tags_list(self, obj):
        return obj.get_tags_list()


# ============================================================================
# DISCOUNT SERIALIZER
# ============================================================================

class DiscountSerializer(serializers.ModelSerializer):
    is_valid = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Discount
        exclude = ['tenant']
        read_only_fields = ['times_used', 'created_at', 'updated_at']


# ============================================================================
# DISCOUNT VALIDATION SERIALIZER
# ============================================================================

class DiscountValidationSerializer(serializers.Serializer):
    """
    For validating discount codes at checkout
    """
    code = serializers.CharField(max_length=50)
    cart_total = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        required=False,
        default=0
    )
    product_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="List of product IDs in cart"
    )

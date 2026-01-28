"""
Complete E-Commerce Views with Multi-Tenant Security
✅ FIXED: All imports and syntax issues resolved
"""
from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count, Avg, Sum
from django.utils import timezone
from decimal import Decimal
import logging

from .models import Product, ProductVariant, Review, Discount
from .serializers import (
    ProductListSerializer, 
    ProductDetailSerializer,
    ProductVariantSerializer,
    ReviewSerializer,
    DiscountSerializer,
    DiscountValidationSerializer
)

logger = logging.getLogger(__name__)


# ============================================================================
# PRODUCT VIEWSET
# ============================================================================

class ProductViewSet(viewsets.ModelViewSet):
    """
    Complete Product API with multi-tenant security
    Auto-filters by tenant, with advanced filtering and search
    """
    
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    # Filtering & Search
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'category', 'is_featured', 'brand', 'is_digital']
    search_fields = ['name', 'description', 'sku', 'tags']
    ordering_fields = ['price', 'created_at', 'name', 'average_rating', 'total_sales']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """✅ SECURE: Tenant-filtered queryset"""
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            logger.warning("ProductViewSet accessed without tenant context")
            return Product.objects.none()
        
        # Start with tenant-filtered queryset
        queryset = Product.objects.filter(tenant=self.request.tenant)
        
        # Public users only see active products
        if not self.request.user.is_authenticated or not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True, published_at__lte=timezone.now())
        
        # Apply query filters
        queryset = self._apply_query_filters(queryset)
        
        # Prefetch related for performance
        queryset = queryset.prefetch_related('images', 'variants')
        
        return queryset
    
    def _apply_query_filters(self, queryset):
        """Apply advanced query filters from URL parameters"""
        # Price range
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        if max_price:
            queryset = queryset.filter(price__lte=max_price)
        
        # Category filter (can be comma-separated)
        category = self.request.query_params.get('category')
        if category:
            categories = [c.strip() for c in category.split(',') if c.strip()]
            queryset = queryset.filter(category__in=categories)
        
        # Tag filter
        tag = self.request.query_params.get('tag')
        if tag:
            queryset = queryset.filter(tags__icontains=tag)
        
        # Stock status
        in_stock = self.request.query_params.get('in_stock')
        if in_stock == 'true':
            queryset = queryset.filter(
                Q(track_inventory=False) | Q(stock__gt=0)
            )
        elif in_stock == 'false':
            queryset = queryset.filter(track_inventory=True, stock=0)
        
        # Sale filter
        on_sale = self.request.query_params.get('on_sale')
        if on_sale == 'true':
            queryset = queryset.exclude(discount_type='none').filter(
                discount_value__gt=0
            ).filter(
                Q(discount_end_date__isnull=True) | Q(discount_end_date__gte=timezone.now())
            )
        
        # Rating filter
        min_rating = self.request.query_params.get('min_rating')
        if min_rating:
            queryset = queryset.filter(average_rating__gte=min_rating)
        
        return queryset
    
    def get_serializer_class(self):
        """Use appropriate serializer for each action"""
        if self.action == 'list':
            return ProductListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ProductDetailSerializer  # Use detail serializer for create/update
        return ProductDetailSerializer
    
    def perform_create(self, serializer):
        """✅ Auto-attach tenant with validation"""
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            raise ValidationError({"detail": "Tenant context required"})
        
        # Only staff can create products
        if not self.request.user.is_staff:
            raise PermissionDenied("Only staff can create products")
        
        serializer.save(tenant=self.request.tenant)
    
    def perform_update(self, serializer):
        """✅ Ensure tenant doesn't change"""
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            raise ValidationError({"detail": "Tenant context required"})
        
        # Only staff can update products
        if not self.request.user.is_staff:
            raise PermissionDenied("Only staff can update products")
        
        serializer.save(tenant=self.request.tenant)
    
    def perform_destroy(self, instance):
        """✅ Only staff can delete products"""
        if not self.request.user.is_staff:
            raise PermissionDenied("Only staff can delete products")
        instance.delete()
    
    def retrieve(self, request, *args, **kwargs):
        """Track product views"""
        instance = self.get_object()
        
        # Increment view count (async or delayed in production)
        instance.increment_view_count()
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    # ============ CUSTOM ACTIONS ============
    
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """GET /api/products/featured/ - Featured products"""
        products = self.get_queryset().filter(is_featured=True)[:12]
        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def bestsellers(self, request):
        """GET /api/products/bestsellers/ - Best selling products"""
        products = self.get_queryset().filter(total_sales__gt=0).order_by('-total_sales')[:12]
        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def on_sale(self, request):
        """GET /api/products/on_sale/ - Products currently on sale"""
        now = timezone.now()
        products = self.get_queryset().exclude(discount_type='none').filter(
            discount_value__gt=0
        ).filter(
            Q(discount_start_date__isnull=True) | Q(discount_start_date__lte=now)
        ).filter(
            Q(discount_end_date__isnull=True) | Q(discount_end_date__gte=now)
        )
        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def new_arrivals(self, request):
        """GET /api/products/new_arrivals/ - Newly added products"""
        cutoff_date = timezone.now() - timezone.timedelta(days=30)
        products = self.get_queryset().filter(
            created_at__gte=cutoff_date
        ).order_by('-created_at')[:12]
        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAdminUser])
    def low_stock(self, request):
        """GET /api/products/low_stock/ - Low stock products (Admin only)"""
        products = [
            product for product in self.get_queryset() 
            if product.is_low_stock
        ]
        serializer = ProductListSerializer(products, many=True, context={'request': request})
        return Response({
            'count': len(products),
            'results': serializer.data
        })
    
    @action(detail=True, methods=['get'])
    def related(self, request, pk=None):
        """GET /api/products/{id}/related/ - Related products"""
        product = self.get_object()
        
        # Find related products by category, tags, or brand
        related = self.get_queryset().filter(
            Q(category=product.category) |
            Q(brand=product.brand)
        ).exclude(id=product.id).distinct()[:8]
        
        serializer = ProductListSerializer(related, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def categories(self, request):
        """GET /api/products/categories/ - All categories with counts"""
        if not hasattr(request, 'tenant') or not request.tenant:
            return Response([], status=status.HTTP_403_FORBIDDEN)
        
        categories = Product.objects.filter(
            tenant=request.tenant,
            is_active=True
        ).exclude(
            category__isnull=True
        ).exclude(
            category=''
        ).values('category').annotate(
            count=Count('id'),
            avg_price=Avg('price')
        ).order_by('category')
        
        return Response(categories)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """GET /api/products/stats/ - Product statistics (Admin only)"""
        if not request.user.is_staff:
            return Response(
                {"detail": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        queryset = self.get_queryset()
        
        stats = {
            'total': queryset.count(),
            'active': queryset.filter(is_active=True).count(),
            'featured': queryset.filter(is_featured=True).count(),
            'out_of_stock': queryset.filter(stock=0, track_inventory=True).count(),
            'low_stock': len([p for p in queryset if p.is_low_stock]),
            'on_sale': queryset.exclude(discount_type='none').count(),
            'total_sales': queryset.aggregate(total=Sum('total_sales'))['total'] or 0,
            'total_views': queryset.aggregate(total=Sum('view_count'))['total'] or 0,
        }
        
        return Response(stats)
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def duplicate(self, request, pk=None):
        """POST /api/products/{id}/duplicate/ - Duplicate product (Admin only)"""
        original = self.get_object()
        
        try:
            # Create duplicate with modified fields
            duplicate = Product(
                tenant=original.tenant,
                name=f"{original.name} (Copy)",
                slug=f"{original.slug}-copy-{timezone.now().strftime('%Y%m%d%H%M')}",
                short_description=original.short_description,
                description=original.description,
                price=original.price,
                cost_price=original.cost_price,
                compare_at_price=original.compare_at_price,
                discount_type=original.discount_type,
                discount_value=original.discount_value,
                stock=original.stock,
                sku=f"{original.sku}-COPY" if original.sku else "",
                category=original.category,
                tags=original.tags,
                brand=original.brand,
                image_url=original.image_url,
                is_active=False,  # Inactive by default
                is_featured=False,
                has_variants=original.has_variants
            )
            duplicate.save()
            
            # Duplicate variants if exists
            if original.has_variants:
                for variant in original.variants.all():
                    variant.pk = None
                    variant.product = duplicate
                    variant.save()
            
            serializer = ProductDetailSerializer(duplicate, context={'request': request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error duplicating product {original.id}: {e}")
            return Response(
                {"detail": "Failed to duplicate product"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================================
# REVIEW VIEWSET
# ============================================================================

class ReviewViewSet(viewsets.ModelViewSet):
    """
    Product Reviews API with multi-tenant security
    """
    
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['rating', 'is_approved', 'is_verified_purchase']
    ordering_fields = ['rating', 'created_at', 'helpful_count']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """✅ SECURE: Tenant-filtered reviews"""
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            return Review.objects.none()
        
        queryset = Review.objects.filter(tenant=self.request.tenant)
        
        # Filter by product if specified
        product_id = self.request.query_params.get('product_id')
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        
        # Non-staff users only see approved reviews
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_approved=True)
        
        return queryset.select_related('product')
    
    def perform_create(self, serializer):
        """✅ Create review with security checks"""
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            raise ValidationError({"detail": "Tenant context required"})
        
        product_id = self.request.data.get('product')
        if not product_id:
            raise ValidationError({"product": "This field is required."})
        
        try:
            # Verify product belongs to tenant
            product = Product.objects.get(
                id=product_id,
                tenant=self.request.tenant
            )
        except Product.DoesNotExist:
            raise ValidationError({"product": "Product not found."})
        
        # Check if user already reviewed this product
        existing_review = Review.objects.filter(
            tenant=self.request.tenant,
            product=product,
            customer_email=serializer.validated_data.get('customer_email')
        ).exists()
        
        if existing_review:
            raise ValidationError({"detail": "You have already reviewed this product."})
        
        # Auto-fill email from authenticated user
        if self.request.user.is_authenticated and not serializer.validated_data.get('customer_email'):
            serializer.validated_data['customer_email'] = self.request.user.email
        
        # Save with tenant and product
        serializer.save(
            tenant=self.request.tenant,
            product=product,
            is_approved=False  # Require admin approval by default
        )
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.AllowAny])
    def mark_helpful(self, request, pk=None):
        """POST /api/reviews/{id}/mark_helpful/"""
        review = self.get_object()
        review.mark_helpful()
        return Response({"helpful_count": review.helpful_count})
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def approve(self, request, pk=None):
        """POST /api/reviews/{id}/approve/ (Admin only)"""
        review = self.get_object()
        review.is_approved = True
        review.save(update_fields=['is_approved'])
        
        # Update product rating
        review.product.update_rating(review.rating)
        
        return Response({"status": "approved"})
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def unapprove(self, request, pk=None):
        """POST /api/reviews/{id}/unapprove/ (Admin only)"""
        review = self.get_object()
        review.is_approved = False
        review.save(update_fields=['is_approved'])
        return Response({"status": "unapproved"})


# ============================================================================
# DISCOUNT VIEWSET
# ============================================================================

class DiscountViewSet(viewsets.ModelViewSet):
    """
    Discount/Coupon Management API with multi-tenant security
    """
    
    serializer_class = DiscountSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['is_active', 'discount_type', 'applies_to']
    search_fields = ['code', 'description']
    
    def get_queryset(self):
        """✅ SECURE: Tenant-filtered discounts"""
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            return Discount.objects.none()
        
        queryset = Discount.objects.filter(tenant=self.request.tenant)
        
        # Public users only see active, valid discounts
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
        
        return queryset.prefetch_related('products')
    
    def perform_create(self, serializer):
        """✅ Create discount with tenant auto-assignment"""
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            raise ValidationError({"detail": "Tenant context required"})
        
        # Only staff can create discounts
        if not self.request.user.is_staff:
            raise PermissionDenied("Only staff can create discounts")
        
        # Auto-uppercase code
        code = serializer.validated_data.get('code', '')
        serializer.validated_data['code'] = code.upper()
        
        serializer.save(tenant=self.request.tenant)
    
    def perform_update(self, serializer):
        """✅ Update discount with tenant check"""
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            raise ValidationError({"detail": "Tenant context required"})
        
        # Only staff can update discounts
        if not self.request.user.is_staff:
            raise PermissionDenied("Only staff can update discounts")
        
        # Ensure tenant doesn't change
        serializer.save(tenant=self.request.tenant)
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def validate(self, request):
        """POST /api/discounts/validate/ - Validate discount code"""
        if not hasattr(request, 'tenant') or not request.tenant:
            return Response(
                {"detail": "Tenant context required"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = DiscountValidationSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            validated_data = serializer.validated_data
            discount = validated_data['discount']
            discount_amount = validated_data['discount_amount']
            cart_total = validated_data.get('cart_total', 0)
            
            response_data = {
                "valid": True,
                "code": discount.code,
                "discount_type": discount.discount_type,
                "discount_value": float(discount.discount_value),
                "discount_amount": float(discount_amount),
                "final_total": float(cart_total - discount_amount),
                "minimum_purchase": float(discount.minimum_purchase),
                "remaining_uses": discount.remaining_uses,
                "description": discount.description
            }
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Discount validation error: {e}")
            return Response(
                {"detail": "Error validating discount"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def increment_usage(self, request, pk=None):
        """POST /api/discounts/{id}/increment_usage/ (Admin only)"""
        discount = self.get_object()
        discount.increment_usage()
        return Response({
            "times_used": discount.times_used,
            "remaining_uses": discount.remaining_uses
        })


# ============================================================================
# PRODUCT VARIANT VIEWSET
# ============================================================================

class ProductVariantViewSet(viewsets.ModelViewSet):
    """
    Product Variants API (optional - can also be accessed via Product detail)
    """
    
    serializer_class = ProductVariantSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['is_active', 'product']
    search_fields = ['sku', 'option1_value', 'option2_value']
    
    def get_queryset(self):
        """✅ SECURE: Tenant-filtered variants"""
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            return ProductVariant.objects.none()
        
        queryset = ProductVariant.objects.filter(tenant=self.request.tenant)
        
        # Public users only see active variants
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
        
        return queryset.select_related('product')

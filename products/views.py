from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.db.models import Q, Avg, Count
from django.utils import timezone
from .models import Product, ProductVariant, Review, Discount
from .serializers import (
    ProductListSerializer, 
    ProductDetailSerializer,
    ReviewSerializer,
    DiscountSerializer,
    DiscountValidationSerializer
)

class ProductViewSet(viewsets.ModelViewSet):
    """
    Complete Product API with filtering, search, and custom endpoints
    """
    permission_classes = [IsAuthenticatedOrReadOnly]
    
    # Filtering & Search
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'category', 'is_featured', 'brand', 'is_digital']
    search_fields = ['name', 'description', 'sku', 'tags']
    ordering_fields = ['price', 'created_at', 'name', 'average_rating', 'total_sales']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """🛡️ Tenant-filtered queryset"""
        if not self.request.tenant:
            return Product.objects.none()
        
        queryset = Product.objects.filter(tenant=self.request.tenant).prefetch_related(
            'variants', 'images', 'reviews'
        )
        
        # Public users only see active products
        if not self.request.user.is_authenticated:
            queryset = queryset.filter(is_active=True)
        
        # Additional filters from query params
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        tag = self.request.query_params.get('tag')
        in_stock = self.request.query_params.get('in_stock')
        on_sale = self.request.query_params.get('on_sale')
        
        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        if max_price:
            queryset = queryset.filter(price__lte=max_price)
        if tag:
            queryset = queryset.filter(tags__icontains=tag)
        if in_stock == 'true':
            queryset = queryset.filter(stock__gt=0)
        if on_sale == 'true':
            queryset = queryset.exclude(discount_type='none')
        
        return queryset
    
    def get_serializer_class(self):
        """Use different serializers for list vs detail"""
        if self.action == 'list':
            return ProductListSerializer
        return ProductDetailSerializer
    
    def perform_create(self, serializer):
        """Auto-attach tenant"""
        if not self.request.tenant:
            raise serializers.ValidationError("Tenant not found")
        serializer.save(tenant=self.request.tenant)
    
    def perform_update(self, serializer):
        """Ensure tenant doesn't change"""
        serializer.save(tenant=self.request.tenant)
    
    def retrieve(self, request, *args, **kwargs):
        """Track product views"""
        instance = self.get_object()
        instance.increment_view_count()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """GET /api/products/featured/"""
        products = self.get_queryset().filter(is_featured=True)[:8]
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def bestsellers(self, request):
        """GET /api/products/bestsellers/"""
        products = self.get_queryset().order_by('-total_sales')[:10]
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def on_sale(self, request):
        """GET /api/products/on_sale/"""
        products = self.get_queryset().exclude(
            discount_type='none'
        ).exclude(discount_value=0)
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def new_arrivals(self, request):
        """GET /api/products/new_arrivals/"""
        # Products from last 30 days
        cutoff_date = timezone.now() - timezone.timedelta(days=30)
        products = self.get_queryset().filter(
            created_at__gte=cutoff_date
        ).order_by('-created_at')[:12]
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticatedOrReadOnly])
    def low_stock(self, request):
        """GET /api/products/low_stock/ (Admin only)"""
        if not request.user.is_authenticated:
            return Response(
                {"detail": "Authentication required"}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        products = [p for p in self.get_queryset() if p.is_low_stock]
        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def related(self, request, pk=None):
        """GET /api/products/{id}/related/"""
        product = self.get_object()
        
        # Find products in same category, excluding current product
        related = self.get_queryset().filter(
            category=product.category
        ).exclude(id=product.id)[:4]
        
        serializer = ProductListSerializer(related, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def categories(self, request):
        """GET /api/products/categories/ - List all categories with counts"""
        categories = self.get_queryset().values('category').annotate(
            count=Count('id')
        ).order_by('category')
        
        return Response(categories)
    
    @action(detail=False, methods=['get'])
    def search_suggestions(self, request):
        """GET /api/products/search_suggestions/?q=shirt"""
        query = request.query_params.get('q', '')
        if len(query) < 2:
            return Response([])
        
        products = self.get_queryset().filter(
            Q(name__icontains=query) | Q(tags__icontains=query)
        )[:5]
        
        suggestions = [p.name for p in products]
        return Response(suggestions)


class ReviewViewSet(viewsets.ModelViewSet):
    """
    Product Reviews API
    """
    serializer_class = ReviewSerializer
    permission_classes = [AllowAny]  # Anyone can read, but create needs validation
    
    def get_queryset(self):
        if not self.request.tenant:
            return Review.objects.none()
        
        queryset = Review.objects.filter(tenant=self.request.tenant)
        
        # Filter by product if specified
        product_id = self.request.query_params.get('product_id')
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        
        # Public users only see approved reviews
        if not self.request.user.is_authenticated:
            queryset = queryset.filter(is_approved=True)
        
        return queryset
    
    def perform_create(self, serializer):
        """Create review for a product"""
        product_id = self.request.data.get('product_id')
        if not product_id:
            raise serializers.ValidationError("product_id is required")
        
        try:
            product = Product.objects.get(id=product_id, tenant=self.request.tenant)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found")
        
        serializer.save(
            tenant=self.request.tenant,
            product=product
        )
    
    @action(detail=True, methods=['post'])
    def mark_helpful(self, request, pk=None):
        """POST /api/reviews/{id}/mark_helpful/"""
        review = self.get_object()
        review.helpful_count += 1
        review.save(update_fields=['helpful_count'])
        return Response({"helpful_count": review.helpful_count})


class DiscountViewSet(viewsets.ModelViewSet):
    """
    Discount/Coupon Management API
    """
    serializer_class = DiscountSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        if not self.request.tenant:
            return Discount.objects.none()
        
        queryset = Discount.objects.filter(tenant=self.request.tenant)
        
        # Public users only see active discounts
        if not self.request.user.is_authenticated:
            queryset = queryset.filter(is_active=True)
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)
    
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def validate(self, request):
        """POST /api/discounts/validate/ - Validate a discount code"""
        serializer = DiscountValidationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        code = serializer.validated_data['code']
        cart_total = serializer.validated_data.get('cart_total', 0)
        
        try:
            discount = Discount.objects.get(
                tenant=request.tenant,
                code__iexact=code
            )
        except Discount.DoesNotExist:
            return Response(
                {"valid": False, "error": "Invalid discount code"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if not discount.is_valid:
            return Response(
                {"valid": False, "error": "This discount code has expired or is no longer valid"}
            )
        
        if cart_total < discount.minimum_purchase:
            return Response({
                "valid": False,
                "error": f"Minimum purchase of ${discount.minimum_purchase} required"
            })
        
        discount_amount = discount.calculate_discount(cart_total)
        
        return Response({
            "valid": True,
            "code": discount.code,
            "discount_type": discount.discount_type,
            "discount_value": float(discount.discount_value),
            "discount_amount": float(discount_amount),
            "final_total": float(cart_total - discount_amount)
        })

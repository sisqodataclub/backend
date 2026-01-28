from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, ReviewViewSet, DiscountViewSet

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
router.register(r'reviews', ReviewViewSet, basename='review')
router.register(r'discounts', DiscountViewSet, basename='discount')

urlpatterns = [
    path('', include(router.urls)),
]

# Available Endpoints:
# 
# PRODUCTS:
# GET    /api/products/                    - List all products (with filters)
# POST   /api/products/                    - Create product (admin)
# GET    /api/products/{id}/               - Get product details
# PUT    /api/products/{id}/               - Update product (admin)
# DELETE /api/products/{id}/               - Delete product (admin)
# GET    /api/products/featured/           - Featured products
# GET    /api/products/bestsellers/        - Best selling products
# GET    /api/products/on_sale/            - Products on sale
# GET    /api/products/new_arrivals/       - Recently added products
# GET    /api/products/low_stock/          - Low stock alert (admin)
# GET    /api/products/{id}/related/       - Related products
# GET    /api/products/categories/         - List categories with counts
# GET    /api/products/search_suggestions/ - Search autocomplete
#
# Query Parameters for /api/products/:
# - category=Electronics
# - is_featured=true
# - brand=Nike
# - min_price=10
# - max_price=100
# - tag=summer
# - in_stock=true
# - on_sale=true
# - search=shirt
# - ordering=price (or -price for descending)
#
# REVIEWS:
# GET    /api/reviews/                     - List all reviews
# POST   /api/reviews/                     - Create review
# GET    /api/reviews/{id}/                - Get review details
# POST   /api/reviews/{id}/mark_helpful/   - Mark review as helpful
#
# Query Parameters for /api/reviews/:
# - product_id=123
#
# DISCOUNTS:
# GET    /api/discounts/                   - List all discounts (admin)
# POST   /api/discounts/                   - Create discount (admin)
# GET    /api/discounts/{id}/              - Get discount details (admin)
# PUT    /api/discounts/{id}/              - Update discount (admin)
# DELETE /api/discounts/{id}/              - Delete discount (admin)
# POST   /api/discounts/validate/          - Validate discount code (public)
#
# Validate discount payload:
# {
#   "code": "SUMMER2024",
#   "cart_total": 100.00
# }

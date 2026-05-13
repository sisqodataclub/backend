# services/urls.py
from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import ServiceViewSet, ServiceBookingViewSet, ServiceCategoryViewSet

router = SimpleRouter()
# ✅ NEW: Register the categories endpoint
router.register(r'service-categories', ServiceCategoryViewSet, basename='service-category')
router.register(r'services', ServiceViewSet, basename='service')
router.register(r'service-bookings', ServiceBookingViewSet, basename='service-booking')

urlpatterns = [
    path('', include(router.urls)),
]

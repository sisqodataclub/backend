from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import ServiceViewSet, ServiceBookingViewSet

# Using SimpleRouter instead of DefaultRouter perfectly bypasses 
# the 'drf_format_suffix' collision bug across multiple apps.
router = SimpleRouter()

router.register(r'services', ServiceViewSet, basename='service')
router.register(r'service-bookings', ServiceBookingViewSet, basename='service-booking')

urlpatterns = [
    path('', include(router.urls)),
]

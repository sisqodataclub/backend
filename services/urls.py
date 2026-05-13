from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ServiceViewSet, ServiceBookingViewSet

# We set include_format_suffixes=False to prevent a known DRF bug 
# where loading multiple routers across different apps causes a 
# "Converter 'drf_format_suffix' is already registered" ValueError.
router = DefaultRouter(include_format_suffixes=False)

router.register(r'services', ServiceViewSet, basename='service')
router.register(r'service-bookings', ServiceBookingViewSet, basename='service-booking')

urlpatterns = [
    path('', include(router.urls)),
]

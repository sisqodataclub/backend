# services/urls.py
from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import (
    ServiceViewSet,
    ServiceBookingViewSet,
    ServiceCategoryViewSet,
    CleaningBookingViewSet,
)

router = SimpleRouter()
router.register(r'service-categories', ServiceCategoryViewSet, basename='service-category')
router.register(r'services', ServiceViewSet, basename='service')
router.register(r'service-bookings', ServiceBookingViewSet, basename='service-booking')
router.register(r'cleaning-bookings', CleaningBookingViewSet, basename='cleaning-booking')

urlpatterns = [
    # Aliases for old endpoints
    path('bookings/', CleaningBookingViewSet.as_view({'post': 'create'}), name='old-booking-alias'),

    # 2. ROUTER LAST: Catches everything else (list, create, detail view lookups)
    path('', include(router.urls)),
]

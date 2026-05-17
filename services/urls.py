# services/urls.py
from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import (
    ServiceViewSet, ServiceBookingViewSet, ServiceCategoryViewSet,
    BookingSnapshotViewSet, CleaningBookingViewSet
)

router = SimpleRouter()
router.register(r'service-categories', ServiceCategoryViewSet, basename='service-category')
router.register(r'services', ServiceViewSet, basename='service')
router.register(r'service-bookings', ServiceBookingViewSet, basename='service-booking')
router.register(r'booking-snapshots', BookingSnapshotViewSet, basename='booking-snapshot')
router.register(r'cleaning-bookings', CleaningBookingViewSet, basename='cleaning-booking')

urlpatterns = [
    path('', include(router.urls)),
    # Aliases for old endpoints (so frontend works without changes)
    path('bookings/', CleaningBookingViewSet.as_view({'post': 'create'}), name='old-booking-alias'),
    # snapshot already registered as booking-snapshots – if old frontend calls exactly /api/booking-snapshots/,
    # we need to ensure the router includes it. The router already does.
]

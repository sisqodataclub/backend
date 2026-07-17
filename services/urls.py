# services/urls.py
from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import (
    ServiceViewSet,
    ServiceBookingViewSet,
    ServiceCategoryViewSet,
    BookingSnapshotViewSet,
    CleaningBookingViewSet,
    ServiceBookingAnalyticsView,   # ✅ NEW analytics view
    get_blocked_times,
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

    # Blocked times endpoint
    path('blocked-times/', get_blocked_times, name='blocked-times'),

    # ✅ NEW: Analytics endpoint for the dashboard
    path('service-bookings/analytics/', ServiceBookingAnalyticsView.as_view(), name='service-booking-analytics'),
]

# services/urls.py
from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import (
    ServiceViewSet,
    ServiceBookingViewSet,
    ServiceCategoryViewSet,
    BookingSnapshotViewSet,
    CleaningBookingViewSet,
    ServiceBookingAnalyticsView,
    get_blocked_times,
    UnpromotedCleaningBookingListView,   # NEW
    promote_cleaning_booking,            # NEW
)

router = SimpleRouter()
router.register(r'service-categories', ServiceCategoryViewSet, basename='service-category')
router.register(r'services', ServiceViewSet, basename='service')
router.register(r'service-bookings', ServiceBookingViewSet, basename='service-booking')
router.register(r'booking-snapshots', BookingSnapshotViewSet, basename='booking-snapshot')
router.register(r'cleaning-bookings', CleaningBookingViewSet, basename='cleaning-booking')

urlpatterns = [
    # 1. EXPLICIT PATHS FIRST: These must be evaluated before the router
    path('service-bookings/analytics/', ServiceBookingAnalyticsView.as_view(), name='service-booking-analytics'),

    # Aliases for old endpoints
    path('bookings/', CleaningBookingViewSet.as_view({'post': 'create'}), name='old-booking-alias'),
    path('blocked-times/', get_blocked_times, name='blocked-times'),

    # NEW: Frontend promotion endpoints
    path('cleaning-bookings/unpromoted/', UnpromotedCleaningBookingListView.as_view(), name='unpromoted-cleaning-bookings'),
    path('cleaning-bookings/<int:pk>/promote/', promote_cleaning_booking, name='promote-cleaning-booking'),

    # 2. ROUTER LAST: Catches everything else (list, create, detail view lookups)
    path('', include(router.urls)),
]

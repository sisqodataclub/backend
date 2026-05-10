from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ServiceViewSet, ServiceBookingViewSet

router = DefaultRouter()
router.register(r'services', ServiceViewSet, basename='service')
router.register(r'service-bookings', ServiceBookingViewSet, basename='service-booking')

urlpatterns = [
    path('', include(router.urls)),
]

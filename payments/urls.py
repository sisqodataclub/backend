"""
Payment URLs
"""
from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import BookingViewSet, stripe_webhook, capture_service_payment

router = SimpleRouter()
router.register(r'bookings', BookingViewSet, basename='booking')

urlpatterns = [
    path('', include(router.urls)),
    path('webhook/', stripe_webhook, name='stripe-webhook'),
    path('capture/<int:booking_id>/', capture_service_payment, name='capture-service-payment'),
]

"""
Payment URLs - Includes e‑commerce bookings + invoice management
"""
from django.urls import path, include
from rest_framework.routers import SimpleRouter, DefaultRouter
from .views import (
    BookingViewSet,
    stripe_webhook,
    capture_service_payment,
    ServiceViewSet,
    InvoiceViewSet,
    CategoryViewSet,
)

booking_router = SimpleRouter()
booking_router.register(r'bookings', BookingViewSet, basename='booking')

invoice_router = DefaultRouter()
invoice_router.register(r'services', ServiceViewSet, basename='service')
invoice_router.register(r'invoices', InvoiceViewSet, basename='invoice')
invoice_router.register(r'categories', CategoryViewSet, basename='category')

urlpatterns = [
    path('', include(booking_router.urls)),
    path('', include(invoice_router.urls)),
    path('webhook/', stripe_webhook, name='stripe-webhook'),
    path('capture/<int:booking_id>/', capture_service_payment, name='capture-service-payment'),
]

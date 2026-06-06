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
    CustomerViewSet,
    InvoiceViewSet,
)

# Router for existing e‑commerce bookings
booking_router = SimpleRouter()
booking_router.register(r'bookings', BookingViewSet, basename='booking')

# Router for invoice‑related endpoints (services, customers, invoices)
invoice_router = DefaultRouter()
invoice_router.register(r'services', ServiceViewSet, basename='service')
invoice_router.register(r'customers', CustomerViewSet, basename='customer')
invoice_router.register(r'invoices', InvoiceViewSet, basename='invoice')

urlpatterns = [
    # Include both routers
    path('', include(booking_router.urls)),
    path('', include(invoice_router.urls)),

    # Webhook & manual capture endpoints
    path('webhook/', stripe_webhook, name='stripe-webhook'),
    path('capture/<int:booking_id>/', capture_service_payment, name='capture-service-payment'),
]

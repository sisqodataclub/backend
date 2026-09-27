# services/views.py
import logging
import stripe
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from rest_framework import generics, permissions, filters, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAuthenticatedOrReadOnly

from django_filters.rest_framework import DjangoFilterBackend

# --- Models ---
from .models import (
    Service,
    ServiceBooking,
    ServiceProvider,
    ServiceCategory,
    BookingSnapshot,
    CleaningBooking,
    BlockedTime,
)

# --- Serializers ---
from .serializers import (
    ServiceSerializer,
    ServiceBookingSerializer,
    CreateServiceBookingSerializer,
    AvailableSlotSerializer,
    ServiceCategorySerializer,
    BookingSnapshotSerializer,
    CleaningBookingSerializer,
    ServiceBookingAnalyticsSerializer,
)

# --- Helpers ---
from .availability import get_available_slots
from payments.views import create_service_payment_intent
from products.models import Discount

# 👇 Import the mapping function
from .mapping import map_cleaning_status_to_service_status

# 👇 Agent API key permission
from services.permissions import HasAgentApiKey

# 👇 Import the notification engine
from customer_notifications.emails import send_arrival_notification, send_completion_and_review

logger = logging.getLogger(__name__)

# PLACEHOLDER — full file content must be fetched and patched, not overwritten.

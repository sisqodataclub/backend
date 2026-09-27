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

# 👇 Import the notification engine
from customer_notifications.emails import send_arrival_notification, send_completion_and_review

# 👇 Restored view definitions (recovered from parent of 22b42f42)
from .restored_views import (
    ServiceBookingAnalyticsView,
    get_blocked_times,
    UnpromotedCleaningBookingListView,
    promote_cleaning_booking,
    CleaningBookingDetailView,
)

logger = logging.getLogger(__name__)


# ============================================================
# HELPER: Resolve cleaning booking items (service IDs → names)
# ============================================================
def get_cleaning_booking_items(cleaning_booking):
    """
    Given a CleaningBooking instance, return a dict of {service_name: quantity}
    including both numeric service IDs and string keys like 'discount'.
    """
    all_items = {
        **cleaning_booking.quantities,
        **cleaning_booking.carpets,
        **cleaning_booking.appliances
    }

    item_names = {}

    # 1. Handle string keys that are NOT numeric IDs
    for key, qty in all_items.items():
        try:
            int(key)
            # It's a numeric ID, handle below
            continue
        except (ValueError, TypeError):
            # It's a string key (e.g., 'discount', 'furnished_fee')
            try:
                qty_int = int(qty)
                if qty_int > 0:
                    item_names[key] = item_names.get(key, 0) + qty_int
            except (ValueError, TypeError):
                pass

    # 2. Handle numeric IDs
    numeric_ids = []
    for key, qty in all_items.items():
        try:
            numeric_ids.append(int(key))
        except (ValueError, TypeError):
            pass

    if numeric_ids:
        services = Service.objects.filter(id__in=numeric_ids)
        services_map = {s.id: s.name for s in services}

        for sid in numeric_ids:
            name = services_map.get(sid)
            if name:
                qty = all_items.get(str(sid), 1)
                try:
                    qty_int = int(qty)
                except (ValueError, TypeError):
                    qty_int = 1
                item_names[name] = item_names.get(name, 0) + qty_int

    return item_names

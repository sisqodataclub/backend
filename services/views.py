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
                    continue
                if qty_int > 0:
                    item_names[name] = item_names.get(name, 0) + qty_int

    return item_names


# ============================================================
# CUSTOM NOTIFICATION ACTIONS (override mixin to accept eta)
# ============================================================
class ServiceBookingViewSet(ModelViewSet):
    serializer_class = ServiceBookingSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return ServiceBooking.objects.all()

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        booking = self.get_object()
        if booking.status != 'pending':
            return Response({"error": "Booking cannot be confirmed"}, status=400)
        booking.status = 'confirmed'
        booking.save()
        return Response({"status": "confirmed"})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        if booking.status not in ['pending', 'confirmed']:
            return Response({"error": "Cannot cancel this booking"}, status=400)
        booking.status = 'cancelled'
        booking.save()
        return Response({"status": "cancelled"})


class ServiceCategoryViewSet(ModelViewSet):
    serializer_class = ServiceCategorySerializer
    permission_classes = [AllowAny]
    queryset = ServiceCategory.objects.all()


class ServiceViewSet(ModelViewSet):
    serializer_class = ServiceSerializer
    permission_classes = [AllowAny]
    queryset = Service.objects.all()


class CleaningBookingViewSet(ModelViewSet):
    serializer_class = CleaningBookingSerializer
    permission_classes = [AllowAny]
    queryset = CleaningBooking.objects.all()

    def get_queryset(self):
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            return CleaningBooking.objects.none()
        return CleaningBooking.objects.filter(tenant=self.request.tenant)

    @action(detail=True, methods=['post'], permission_classes=[AllowAny])
    def confirm(self, request, pk=None):
        """Confirm a CleaningBooking.

        The frontend posts to /api/cleaning-bookings/<pk>/confirm/ with the
        booking details (selected_datetime, payment_method, property_details,
        phone). The lookup uses the tenant-scoped queryset so cross-tenant
        confirmation is impossible.
        """
        booking = self.get_object()

        data = request.data or {}

        # Persist any fields the customer may have edited on the checkout page.
        selected_datetime = data.get('selected_datetime')
        if isinstance(selected_datetime, dict):
            booking.selected_datetime = {
                'booking_date': selected_datetime.get('booking_date', ''),
                'timeslot': selected_datetime.get('timeslot', ''),
            }

        payment_method = data.get('payment_method')
        if payment_method:
            booking.payment_method = payment_method

        property_details = data.get('property_details')
        if isinstance(property_details, dict):
            booking.property_details = {
                'address': property_details.get('address', ''),
                'postcode': property_details.get('postcode', ''),
            }

        phone = data.get('phone')
        if phone is not None:
            booking.phone = phone

        if booking.status != 'confirmed':
            booking.status = 'confirmed'

        booking.save()
        return Response({"status": "confirmed", "booking_id": booking.id})

    def create(self, request, *args, **kwargs):
        tenant = request.tenant
        if not tenant:
            return Response({"error": "Tenant not identified"}, status=400)

        data = request.data
        session_id = data.get('session_id')

        if session_id and CleaningBooking.objects.filter(session_id=session_id, tenant=tenant).exists():
            return Response(
                {"error": "This booking has already been submitted. Please refresh the page."},
                status=409
            )

        frontend_total = data.get('total')
        if frontend_total is None or frontend_total <= 0:
            return Response({"error": "Invalid total amount"}, status=400)

        payment_link = ""
        if data.get('payment_method') == 'card':
            try:
                session = stripe.checkout.Session.create(
                    success_url=data.get('success_url', 'https://core.franciscodes.com/success'),
                    cancel_url=data.get('cancel_url', 'https://core.franciscodes.com/cancel'),
                    payment_method_types=["card"],
                    line_items=[{
                        "price_data": {
                            "currency": "gbp",
                            "unit_amount": int(frontend_total * 100),
                            "product_data": {"name": "Cleaning Service"},
                        },
                        "quantity": 1,
                    }],
                    mode="payment",
                )
                payment_link = session.url
            except Exception as e:
                return Response({"error": f"Stripe error: {str(e)}"}, status=500)

        booking = CleaningBooking.objects.create(
            tenant=tenant,
            session_id=session_id,
            customer_name=data.get('name', ''),
            customer_email=data.get('email'),
            phone=data.get('phone', ''),
            selected_areas=data.get('selected_areas', []),
            quantities=data.get('quantities', {}),
            carpets=data.get('carpets', {}),
            appliances=data.get('appliances', {}),
            furnished_status=data.get('furnished_status', ''),
            parking=data.get('parking', ''),
            biohazard=data.get('biohazard', ''),
            payment_method=data.get('payment_method', 'unknown'),
            total=frontend_total,
            paymentlink=payment_link,
            property_details={'address': data.get('address', ''), 'postcode': data.get('postcode', '')},
            selected_datetime={'booking_date': data.get('booking_date', ''), 'timeslot': data.get('timeslot', '')},
        )

        # Send quote summary email
        try:
            item_names = {}
            items_breakdown = data.get('items_breakdown', [])
            if items_breakdown:
                for line in items_breakdown:
                    name = line.get('name')
                    qty = line.get('quantity')
                    if name and qty and qty > 0:
                        item_names[name] = qty
            else:
                for key, qty in data.get('quantities', {}).items():
                    try:
                        qty_int = int(qty)
                        if qty_int > 0:
                            item_names[f"Item {key}"] = qty_int
                    except (ValueError, TypeError):
                        pass

            item_names["---"] = "---"
            if booking.customer_name:
                item_names["Name"] = booking.customer_name

            if booking.furnished_status:
                item_names["Furnished Status"] = booking.furnished_status.title()
            if booking.parking:
                item_names["Parking"] = booking.parking.title()
            if booking.biohazard:
                item_names["Biohazard"] = booking.biohazard.title()
            if booking.payment_method:
                item_names["Payment Method"] = booking.payment_method.title()

            booking_date = booking.selected_datetime.get('booking_date')
            timeslot = booking.selected_datetime.get('timeslot')
            if booking_date:
                item_names["Booking Date"] = booking_date
            if timeslot:
                item_names["Timeslot"] = timeslot
            if booking.property_details.get('address'):
                item_names["Address"] = booking.property_details['address']
            if booking.property_details.get('postcode'):
                item_names["Postcode"] = booking.property_details['postcode']

            plain_text_items = "\n".join([f"- {k}: {v}" for k, v in item_names.items() if k != "---"])
            plain_message = (
                f"Your Quote Summary 🎉\n\n"
                f"Quote ID: {booking.id}\n\n"
                f"Summary:\n{plain_text_items}\n\n"
                f"Total Quote: £{frontend_total}\n\n"
                f"Follow the link below to complete your booking.\n"
                f"https://api.ddeepcleaningservices.com/booking?quote_id={booking.id}\n\n"
                f"Thank you for choosing Ddeep Cleaning Services!"
            )
            html_message = render_to_string('quote_booking.html', {
                'booking_id': booking.id,
                'total_quote': frontend_total,
                'booking_items': item_names,
            })
            send_mail(
                subject="Your Quote Summary – Ddeep Cleaning Services",
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[booking.customer_email, 'fd92uk@gmail.com'],
                html_message=html_message,
                fail_silently=False,
            )
        except Exception as e:
            logger.warning(f"Quote summary email failed: {e}")

        return Response({
            "status": "success",
            "booking_id": booking.id,
            "paymentlink": payment_link,
            "total": frontend_total,
        }, status=201)

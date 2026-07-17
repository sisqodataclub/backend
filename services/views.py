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
    ServiceBookingAnalyticsSerializer,  # NEW
)

# --- Helpers ---
from .availability import get_available_slots
from payments.views import create_service_payment_intent
from products.models import Discount

logger = logging.getLogger(__name__)


# ============================================================
# 1. CATEGORY VIEWSET
# ============================================================
class ServiceCategoryViewSet(ModelViewSet):
    """Allows frontend to fetch categories (e.g., for navigation tabs)"""
    queryset = ServiceCategory.objects.all()
    serializer_class = ServiceCategorySerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            return ServiceCategory.objects.none()
        return self.queryset.filter(tenant_id=self.request.tenant.id, is_active=True)


# ============================================================
# 2. SERVICE VIEWSET
# ============================================================
class ServiceViewSet(ModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            logger.warning("ServiceViewSet accessed without tenant context")
            return Service.objects.none()

        queryset = self.queryset.filter(tenant_id=self.request.tenant.id, is_active=True)

        # Filtering
        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        category_name = self.request.query_params.get('category_name')
        if category_name:
            queryset = queryset.filter(category__name__iexact=category_name)

        include_addons = self.request.query_params.get('include_addons')
        if not include_addons or include_addons.lower() == 'false':
            queryset = queryset.filter(is_addon_only=False)

        return queryset

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def calculate_quote(self, request):
        tenant = request.tenant
        if not tenant:
            return Response({"error": "Tenant not identified"}, status=400)

        items = request.data.get('items', [])
        furnished = request.data.get('furnished_status')
        biohazard = request.data.get('biohazard')
        discount_code = request.data.get('discount_code')

        subtotal = 0.0
        breakdown = []

        for item in items:
            service_id = item.get('service_id')
            quantity = item.get('quantity', 1)
            try:
                service = Service.objects.get(id=service_id, tenant=tenant, is_active=True)
            except Service.DoesNotExist:
                return Response({"error": f"Service ID {service_id} not found"}, status=400)

            if service.price_fixed:
                unit_price = float(service.price_fixed)
            elif service.price_per_hour:
                hours = service.duration_minutes / 60
                unit_price = float(service.price_per_hour) * hours
            else:
                return Response({"error": f"Service '{service.name}' has no price"}, status=400)

            line_total = unit_price * quantity
            subtotal += line_total
            breakdown.append({
                "name": service.name,
                "quantity": quantity,
                "unit_price": round(unit_price, 2),
                "total": round(line_total, 2)
            })

        fees = 0.0
        if furnished == "furnished":
            fees += 10.0
            breakdown.append({"name": "Furnished Property Fee", "total": 10.0})
        if biohazard == "yes-human":
            fees += 25.0
            breakdown.append({"name": "Biohazard (Human)", "total": 25.0})
        elif biohazard == "yes-animal":
            fees += 15.0
            breakdown.append({"name": "Biohazard (Animal)", "total": 15.0})
        elif biohazard == "yes-blood":
            fees += 40.0
            breakdown.append({"name": "Biohazard (Blood)", "total": 40.0})

        discount_amount = 0.0
        if discount_code:
            try:
                discount = Discount.objects.get(code__iexact=discount_code, tenant=tenant, is_active=True)
                discount_amount = discount.calculate_discount(subtotal + fees)
                breakdown.append({"name": f"Discount ({discount.code})", "total": -discount_amount})
            except Discount.DoesNotExist:
                return Response({"error": "Invalid discount code"}, status=400)

        total = max(0.0, subtotal + fees - discount_amount)

        return Response({
            "subtotal": round(subtotal, 2),
            "fees": round(fees, 2),
            "discount": round(discount_amount, 2),
            "total": round(total, 2),
            "breakdown": breakdown
        })

    @action(detail=True, methods=['get'])
    def available_slots(self, request, pk=None):
        service = self.get_object()
        date_str = request.query_params.get('date')
        provider_id = request.query_params.get('provider_id')

        if not date_str:
            return Response({"error": "date parameter required"}, status=400)

        try:
            naive_date = datetime.strptime(date_str, '%Y-%m-%d')
            date = timezone.make_aware(naive_date)
        except Exception:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400)

        slots = get_available_slots(
            service_id=service.id,
            date=date,
            tenant_id=request.tenant.id,
            provider_id=provider_id
        )
        return Response(slots)


# ============================================================
# 3. SERVICE BOOKING VIEWSET (Time-slot appointments)
# ============================================================
class ServiceBookingViewSet(ModelViewSet):
    serializer_class = ServiceBookingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            logger.warning("ServiceBookingViewSet accessed without tenant context")
            return ServiceBooking.objects.none()

        user = self.request.user
        if user.is_staff:
            return ServiceBooking.objects.filter(tenant_id=self.request.tenant.id)

        return ServiceBooking.objects.filter(
            tenant_id=self.request.tenant.id,
            customer_email=user.email
        )

    def create(self, request, *args, **kwargs):
        create_serializer = CreateServiceBookingSerializer(data=request.data)
        create_serializer.is_valid(raise_exception=True)
        data = create_serializer.validated_data

        service = get_object_or_404(Service, id=data['service_id'], tenant_id=request.tenant.id)
        start = data['start_time']
        end = start + timedelta(minutes=service.duration_minutes)

        slots = get_available_slots(service.id, start, request.tenant.id, data.get('provider_id'))
        if not any(slot['start'] == start for slot in slots):
            return Response({"error": "Slot no longer available"}, status=409)

        provider_id = data.get('provider_id')
        if not provider_id and service.any_staff_can_serve:
            matching_slot = next(s for s in slots if s['start'] == start)
            provider_id = matching_slot['provider_ids'][0]

        booking = ServiceBooking.objects.create(
            tenant=request.tenant,
            service=service,
            provider_id=provider_id,
            customer_email=data['customer_email'],
            customer_name=data.get('customer_name', ''),
            start_time=start,
            end_time=end,
            total_price=service.calculate_price(),
            status='pending',
            customer_notes=data.get('customer_notes', '')
        )

        payment_intent = create_service_payment_intent(booking)
        booking.stripe_payment_intent_id = payment_intent.id
        booking.save(update_fields=['stripe_payment_intent_id'])

        return Response({
            'booking': ServiceBookingSerializer(booking).data,
            'client_secret': payment_intent.client_secret
        }, status=201)

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


# ============================================================
# 4. ANALYTICS VIEW (for the dashboard)
# ============================================================
class ServiceBookingAnalyticsView(generics.ListAPIView):
    """
    API endpoint for the analytics dashboard.
    Returns all bookings with all analytical fields, filterable and searchable.
    """
    serializer_class = ServiceBookingAnalyticsSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        'payment_status',
        'status',  # job status
        'has_complaint',
        'rating',
        'review_request_sent',
        'utm_source',
        'utm_medium',
        'completed_at__date',
        'payment_date__date',
    ]
    search_fields = ['customer_name', 'customer_email', 'service__name', 'complaint_notes', 'internal_notes']
    ordering_fields = ['created_at', 'total_price', 'customer_name', 'completed_at', 'payment_date']
    ordering = ['-created_at']

    def get_queryset(self):
        tenant = self.request.tenant
        if not tenant:
            return ServiceBooking.objects.none()
        return ServiceBooking.objects.filter(tenant=tenant).select_related('service', 'provider', 'cleaning_booking')


# ============================================================
# 5. BOOKING SNAPSHOT VIEWSET
# ============================================================
class BookingSnapshotViewSet(ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = BookingSnapshotSerializer

    def get_queryset(self):
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            return BookingSnapshot.objects.none()
        return BookingSnapshot.objects.filter(tenant=self.request.tenant)

    def create(self, request, *args, **kwargs):
        tenant = request.tenant
        if not tenant:
            return Response({"error": "Tenant not identified"}, status=400)

        session_id = request.data.get('session_id')
        if not session_id:
            return Response({"error": "session_id required"}, status=400)

        snapshot, created = BookingSnapshot.objects.update_or_create(
            tenant=tenant,
            session_id=session_id,
            defaults={'data': request.data, 'is_final': False}
        )
        return Response({"status": "saved", "snapshot_id": snapshot.id}, status=200)


# ============================================================
# 6. CLEANING BOOKING VIEWSET (Wizard-style bookings)
# ============================================================
class CleaningBookingViewSet(ModelViewSet):
    serializer_class = CleaningBookingSerializer
    permission_classes = [AllowAny]
    queryset = CleaningBooking.objects.all()

    def get_queryset(self):
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            return CleaningBooking.objects.none()
        return CleaningBooking.objects.filter(tenant=self.request.tenant)

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
            if booking.customer_email:
                item_names["Email"] = booking.customer_email
            if booking.phone:
                item_names["Phone"] = booking.phone
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
                recipient_list=[booking.customer_email, 'francis@dataclubcenter.com'],
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

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', True)
        instance = self.get_object()
        data = request.data

        old_status = instance.status
        status_changed_to_confirmed = False

        if 'payment_method' in data:
            instance.payment_method = data['payment_method']
        if 'selected_datetime' in data:
            instance.selected_datetime = data['selected_datetime']
        if 'status' in data:
            instance.status = data['status']
            if data['status'] == 'confirmed' and old_status != 'confirmed':
                status_changed_to_confirmed = True
        if 'phone' in data:
            instance.phone = data['phone']
        if 'property_details' in data:
            current_details = instance.property_details or {}
            current_details.update(data['property_details'])
            instance.property_details = current_details

        payment_link = instance.paymentlink
        if instance.payment_method == 'card' and instance.total > 0:
            try:
                session = stripe.checkout.Session.create(
                    success_url=data.get('success_url', 'https://core.franciscodes.com/success'),
                    cancel_url=data.get('cancel_url', 'https://core.franciscodes.com/cancel'),
                    payment_method_types=["card"],
                    line_items=[{
                        "price_data": {
                            "currency": "gbp",
                            "unit_amount": int(instance.total * 100),
                            "product_data": {"name": "Cleaning Service"},
                        },
                        "quantity": 1,
                    }],
                    mode="payment",
                )
                payment_link = session.url
            except Exception as e:
                return Response({"error": f"Stripe error: {str(e)}"}, status=500)

        instance.paymentlink = payment_link
        instance.save(update_fields=[
            'payment_method', 'selected_datetime', 'status', 'paymentlink', 'property_details', 'phone'
        ])

        if status_changed_to_confirmed:
            try:
                item_names = {}
                all_items = {**instance.quantities, **instance.carpets, **instance.appliances}

                base_areas_to_skip = set()
                for key in all_items.keys():
                    if isinstance(key, str) and '_' in key:
                        base = key.split('_')[0]
                        base_areas_to_skip.add(base)

                for area in (instance.selected_areas or []):
                    if isinstance(area, str) and not area.isdigit() and area not in base_areas_to_skip:
                        item_names[area] = 1

                numeric_ids = []
                for key, qty in all_items.items():
                    try:
                        int(key)
                        numeric_ids.append(int(key))
                    except (ValueError, TypeError):
                        try:
                            qty_int = int(qty)
                            if qty_int > 0:
                                item_names[key] = item_names.get(key, 0) + qty_int
                        except (ValueError, TypeError):
                            pass

                services_map = {}
                if numeric_ids:
                    services = Service.objects.filter(id__in=numeric_ids)
                    services_map = {s.id: s.name for s in services}
                    missing = set(numeric_ids) - set(services_map.keys())
                    if missing:
                        logger.warning(f"Booking {instance.id}: missing service IDs {missing}")

                for sid in numeric_ids:
                    name = services_map.get(sid)
                    if name:
                        qty = all_items.get(str(sid), 1)
                        try:
                            qty_int = int(qty)
                        except (ValueError, TypeError):
                            qty_int = 1
                        if qty_int > 0:
                            item_names[name] = item_names.get(name, 0) + qty_int

                item_names["---"] = "---"
                if instance.customer_name:
                    item_names["Name"] = instance.customer_name
                if instance.customer_email:
                    item_names["Email"] = instance.customer_email
                if instance.phone:
                    item_names["Phone"] = instance.phone
                if instance.furnished_status:
                    item_names["Furnished Status"] = instance.furnished_status.title()
                if instance.parking:
                    item_names["Parking"] = instance.parking.title()
                if instance.biohazard:
                    item_names["Biohazard"] = instance.biohazard.title()
                if instance.payment_method:
                    item_names["Payment Method"] = instance.payment_method.title()
                if instance.selected_datetime.get('booking_date'):
                    item_names["Booking Date"] = instance.selected_datetime['booking_date']
                if instance.selected_datetime.get('timeslot'):
                    item_names["Timeslot"] = instance.selected_datetime['timeslot']
                if instance.property_details.get('address'):
                    item_names["Address"] = instance.property_details['address']
                if instance.property_details.get('postcode'):
                    item_names["Postcode"] = instance.property_details['postcode']

                html_message = render_to_string('thankyou.html', {
                    'booking_id': instance.id,
                    'total_quote': instance.total,
                    'booking_items': item_names,
                })
                plain_message = strip_tags(html_message)
                send_mail(
                    subject="Booking Confirmed!",
                    message=plain_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[instance.customer_email, 'francis@dataclubcenter.com'],
                    html_message=html_message,
                    fail_silently=False,
                )
            except Exception as e:
                logger.warning(f"Booking confirmation email failed: {e}")

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)


# ============================================================
# 7. BLOCKED TIMES API
# ============================================================
@api_view(['GET'])
@permission_classes([AllowAny])
def get_blocked_times(request):
    today = timezone.now().date()
    blocks = BlockedTime.objects.filter(date__gte=today)

    fully_blocked_dates = []
    partially_blocked_slots = {}

    for block in blocks:
        date_str = block.date.isoformat()
        if not block.timeslot:
            fully_blocked_dates.append(date_str)
        else:
            if date_str not in partially_blocked_slots:
                partially_blocked_slots[date_str] = []
            partially_blocked_slots[date_str].append(block.timeslot)

    return Response({
        "fully_blocked_dates": fully_blocked_dates,
        "partially_blocked_slots": partially_blocked_slots
    })

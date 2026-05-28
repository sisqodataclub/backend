import logging
from datetime import datetime, timedelta
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import permissions
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny


from .models import (
       Service,
       ServiceBooking,
       ServiceProvider,
       ServiceCategory,
       BookingSnapshot,    # 👈 Added
       CleaningBooking,
       BlockedTime     # 👈 Added
   )



from .serializers import (
    ServiceSerializer,
    ServiceBookingSerializer,
    CreateServiceBookingSerializer,
    AvailableSlotSerializer,
    ServiceCategorySerializer,
    BookingSnapshotSerializer,    # 👈 add this
    CleaningBookingSerializer     # 👈 add this
)



from .availability import get_available_slots
from payments.views import create_service_payment_intent
from products.models import Discount   # ✅ Import Discount model for validation

logger = logging.getLogger(__name__)


# ==========================================
# Category ViewSet
# ==========================================
class ServiceCategoryViewSet(ModelViewSet):
    """Allows frontend to fetch categories (e.g., for navigation tabs)"""
    queryset = ServiceCategory.objects.all()
    serializer_class = ServiceCategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            return ServiceCategory.objects.none()
        return self.queryset.filter(tenant_id=self.request.tenant.id, is_active=True)


# ==========================================
# Service ViewSet with category_name filter
# ==========================================
class ServiceViewSet(ModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        """Tenant‑filtered queryset with query params for category (ID or name) and add‑ons."""
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            logger.warning("ServiceViewSet accessed without tenant context")
            return Service.objects.none()

        queryset = self.queryset.filter(tenant_id=self.request.tenant.id, is_active=True)

        # Filter by category ID (e.g. ?category=4)
        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        # NEW: Filter by category name (case‑insensitive, e.g. ?category_name=cleaning_services)
        category_name = self.request.query_params.get('category_name')
        if category_name:
            queryset = queryset.filter(category__name__iexact=category_name)

        # Filter out add‑on services unless explicitly requested
        include_addons = self.request.query_params.get('include_addons')
        if not include_addons or include_addons.lower() == 'false':
            queryset = queryset.filter(is_addon_only=False)

        return queryset

    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def calculate_quote(self, request):
        """
        POST /api/services/calculate_quote/
        Securely calculates the total price using database prices.
        Request body:
        {
            "items": [{"service_id": 1, "quantity": 2}, ...],
            "furnished_status": "furnished",   # optional
            "biohazard": "yes-human",           # optional
            "discount_code": "SAVE10"           # optional
        }
        """
        tenant = request.tenant
        if not tenant:
            return Response({"error": "Tenant not identified"}, status=400)

        items = request.data.get('items', [])
        furnished = request.data.get('furnished_status')
        biohazard = request.data.get('biohazard')
        discount_code = request.data.get('discount_code')

        subtotal = 0.0
        breakdown = []

        # 1. Validate each item and calculate subtotal
        for item in items:
            service_id = item.get('service_id')
            quantity = item.get('quantity', 1)
            try:
                service = Service.objects.get(id=service_id, tenant=tenant, is_active=True)
            except Service.DoesNotExist:
                return Response({"error": f"Service ID {service_id} not found"}, status=400)

            # Determine unit price
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

        # 2. Fees
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

        # 3. Discount validation
        discount_amount = 0.0
        if discount_code:
            try:
                discount = Discount.objects.get(
                    code__iexact=discount_code,
                    tenant=tenant,
                    is_active=True
                )
                # You may add additional checks: expiry, min purchase, remaining uses
                # Here we use a simple flat discount for example
                # Modify based on your Discount model method
                discount_amount = discount.calculate_discount(subtotal + fees)
                breakdown.append({"name": f"Discount ({discount.code})", "total": -discount_amount})
            except Discount.DoesNotExist:
                return Response({"error": "Invalid discount code"}, status=400)

        total = subtotal + fees - discount_amount
        total = max(0.0, total)

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


# ==========================================
# ServiceBooking ViewSet (unchanged)
# ==========================================
class ServiceBookingViewSet(ModelViewSet):
    serializer_class = ServiceBookingSerializer
    permission_classes = [permissions.IsAuthenticated]

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

        slots = get_available_slots(
            service.id,
            start,
            request.tenant.id,
            data.get('provider_id')
        )
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




# ==========================================
# NEW: Secure Cleaning Booking ViewSet
# ==========================================
from django.conf import settings
import stripe
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

stripe.api_key = settings.STRIPE_SECRET_KEY


class BookingSnapshotViewSet(ModelViewSet):
    permission_classes = [permissions.AllowAny]
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




# services/views.py – CleaningBookingViewSet (complete)

# services/views.py – CleaningBookingViewSet (complete)
# services/views.py – CleaningBookingViewSet (complete, with update support)


# services/views.py – CleaningBookingViewSet (final, with variation names in final email)

from rest_framework.viewsets import ModelViewSet
from rest_framework import permissions
from rest_framework.response import Response
from .models import CleaningBooking, Service
from .serializers import CleaningBookingSerializer
import stripe
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging

logger = logging.getLogger(__name__)

class CleaningBookingViewSet(ModelViewSet):
    serializer_class = CleaningBookingSerializer
    permission_classes = [permissions.AllowAny]
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

        # Prevent duplicate booking
        if session_id and CleaningBooking.objects.filter(session_id=session_id, tenant=tenant).exists():
            return Response(
                {"error": "This booking has already been submitted. Please refresh the page."},
                status=409
            )

        frontend_total = data.get('total')
        if frontend_total is None or frontend_total <= 0:
            return Response({"error": "Invalid total amount"}, status=400)

        # Stripe payment link (if card)
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

        # Save booking
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
            property_details={
                'address': data.get('address', ''),
                'postcode': data.get('postcode', ''),
            },
            selected_datetime={
                'booking_date': data.get('booking_date', ''),
                'timeslot': data.get('timeslot', ''),
            },
        )

        # Send quote summary email (quote_booking.html)
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
        """
        Handle PATCH requests to update a quote (date, time, payment method, status,
        address, phone). Also sends a final booking confirmation email when status becomes 'confirmed'.
        This version shows variation names (e.g., "Kitchen Small") and skips base areas when variations are present.
        """
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

        # Stripe payment link (if card)
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

        # Send final confirmation email if status changed to 'confirmed'
        if status_changed_to_confirmed:
            try:
                item_names = {}

                # 1. Merge all quantified items (quantities, carpets, appliances)
                all_items = {**instance.quantities, **instance.carpets, **instance.appliances}

                # 2. Determine which base areas have variations selected
                base_areas_to_skip = set()
                for key in all_items.keys():
                    if isinstance(key, str) and '_' in key:
                        base = key.split('_')[0]
                        base_areas_to_skip.add(base)

                # 3. Process selected_areas – keep only base areas that are NOT skipped
                for area in (instance.selected_areas or []):
                    if isinstance(area, str) and not area.isdigit():
                        if area not in base_areas_to_skip:
                            item_names[area] = 1

                # 4. Separate numeric IDs from other (string) keys
                numeric_ids = []
                other_items = {}
                for key, qty in all_items.items():
                    try:
                        int(key)
                        numeric_ids.append(int(key))
                    except (ValueError, TypeError):
                        other_items[key] = qty

                # 5. Fetch service names for all numeric IDs (no tenant / active filters)
                services_map = {}
                if numeric_ids:
                    services = Service.objects.filter(id__in=numeric_ids)
                    services_map = {s.id: s.name for s in services}

                # 6. Add resolved service names (these include variations like "Kitchen_Small")
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
                    else:
                        logger.warning(f"Service ID {sid} not found for booking {instance.id}")

                # 7. Add other (non‑numeric) items directly (e.g., fee keys)
                for key, qty in other_items.items():
                    try:
                        qty_int = int(qty)
                    except (ValueError, TypeError):
                        qty_int = 1
                    if qty_int > 0:
                        item_names[key] = item_names.get(key, 0) + qty_int

                # 8. Add personal details
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

                # 9. Send email
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
        """Allow PATCH requests (partial updates)."""
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)








@api_view(['GET'])
@permission_classes([AllowAny])
def get_blocked_times(request):
    today = timezone.now().date()
    
    # Only fetch blocked dates from today onwards to keep the payload small
    blocks = BlockedTime.objects.filter(date__gte=today)
    
    fully_blocked_dates = []
    partially_blocked_slots = {}

    for block in blocks:
        date_str = block.date.isoformat() # Converts to "YYYY-MM-DD"
        
        if not block.timeslot:
            # If timeslot is blank, the whole day is blocked
            fully_blocked_dates.append(date_str)
        else:
            # If there is a specific timeslot, add it to that date's list
            if date_str not in partially_blocked_slots:
                partially_blocked_slots[date_str] = []
            partially_blocked_slots[date_str].append(block.timeslot)

    return Response({
        "fully_blocked_dates": fully_blocked_dates,
        "partially_blocked_slots": partially_blocked_slots
    })





import logging
from datetime import datetime, timedelta
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import permissions
from django.shortcuts import get_object_or_404
from django.utils import timezone


from .models import (
       Service, 
       ServiceBooking, 
       ServiceProvider, 
       ServiceCategory,
       BookingSnapshot,    # 👈 Added
       CleaningBooking     # 👈 Added
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





# services/views.py (CleaningBookingViewSet only – keep other code unchanged)

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

        # Helper to safely convert a value to integer
        def to_int(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0

        # --- Build items list for price calculation ---
        items = []

        # 1. Selected areas (area names)
        for area in data.get('selected_areas', []):
            service = Service.objects.filter(name=area, tenant=tenant, is_active=True).first()
            if service:
                items.append({"service_id": service.id, "quantity": 1})

        # 2. Quantities (keys can be service IDs or names)
        for sid, qty in data.get('quantities', {}).items():
            qty = to_int(qty)
            if qty > 0:
                try:
                    service_id = int(sid)
                    if Service.objects.filter(id=service_id, tenant=tenant).exists():
                        items.append({"service_id": service_id, "quantity": qty})
                except ValueError:
                    service = Service.objects.filter(name=sid, tenant=tenant, is_active=True).first()
                    if service:
                        items.append({"service_id": service.id, "quantity": qty})

        # 3. Carpets and appliances
        for dict_obj in (data.get('carpets', {}), data.get('appliances', {})):
            for sid, qty in dict_obj.items():
                qty = to_int(qty)
                if qty > 0:
                    try:
                        service_id = int(sid)
                        if Service.objects.filter(id=service_id, tenant=tenant).exists():
                            items.append({"service_id": service_id, "quantity": qty})
                    except ValueError:
                        service = Service.objects.filter(name=sid, tenant=tenant, is_active=True).first()
                        if service:
                            items.append({"service_id": service.id, "quantity": qty})

        # --- Calculate subtotal from items ---
        subtotal = 0.0
        for item in items:
            service_id = item['service_id']
            quantity = item['quantity']
            try:
                service = Service.objects.get(id=service_id, tenant=tenant, is_active=True)
            except Service.DoesNotExist:
                return Response({"error": f"Service {service_id} not found"}, status=400)
            if service.price_fixed:
                unit_price = float(service.price_fixed)
            elif service.price_per_hour:
                unit_price = float(service.price_per_hour) * (service.duration_minutes / 60)
            else:
                continue
            subtotal += unit_price * quantity

        # --- Fees ---
        fees = 0.0
        furnished = data.get('furnished_status')
        biohazard = data.get('biohazard')
        if furnished == 'furnished':
            fees += 10.0
        if biohazard == 'yes-human':
            fees += 25.0
        elif biohazard == 'yes-animal':
            fees += 15.0
        elif biohazard == 'yes-blood':
            fees += 40.0

        # --- Discount ---
        discount_amount = 0.0
        discount_code = data.get('discount_code')
        if discount_code:
            try:
                from products.models import Discount
                discount = Discount.objects.get(code__iexact=discount_code, tenant=tenant, is_active=True)
                discount_amount = discount.calculate_discount(subtotal + fees)
            except Discount.DoesNotExist:
                pass

        final_total = subtotal + fees - discount_amount
        final_total = max(0.0, final_total)

        if final_total <= 0:
            return Response({"error": "Invalid total amount"}, status=400)

        # --- Stripe payment link (if card payment) ---
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
                            "unit_amount": int(final_total * 100),
                            "product_data": {"name": "Cleaning Service"},
                        },
                        "quantity": 1,
                    }],
                    mode="payment",
                )
                payment_link = session.url
            except Exception as e:
                return Response({"error": f"Stripe error: {str(e)}"}, status=500)

        # --- Save booking ---
        booking = CleaningBooking.objects.create(
            tenant=tenant,
            session_id=data.get('session_id'),
            customer_name=data.get('name', ''),
            customer_email=data.get('email'),
            phone=data.get('phone', ''),
            selected_areas=data.get('selected_areas', []),
            quantities=data.get('quantities', {}),
            carpets=data.get('carpets', {}),
            appliances=data.get('appliances', {}),
            furnished_status=furnished or '',
            parking=data.get('parking', ''),
            biohazard=biohazard or '',
            payment_method=data.get('payment_method', 'unknown'),
            total=final_total,
            paymentlink=payment_link,
        )

        # --- Send confirmation email ---
        try:
            html_message = render_to_string('thankyou.html', {
                'booking': booking,
                'booking_items': {**booking.quantities, **booking.carpets, **booking.appliances},
                'total_quote': final_total,
                'phone': booking.phone,
                'parking': booking.parking,
                'furnished': booking.furnished_status,
                'booking_id': booking.id,
            })
            plain_message = strip_tags(html_message)
            send_mail(
                subject="Booking Confirmation",
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[booking.customer_email, 'francis@dataclubcenter.com'],
                html_message=html_message,
                fail_silently=False,
            )
        except Exception as e:
            logger.warning(f"Email send failed: {e}")

        return Response({
            "status": "success",
            "booking_id": booking.id,
            "paymentlink": payment_link,
            "total": final_total,
        }, status=201)

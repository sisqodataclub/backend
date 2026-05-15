import logging
from datetime import datetime, timedelta
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import permissions
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Service, ServiceBooking, ServiceProvider, ServiceCategory
from .serializers import (
    ServiceSerializer,
    ServiceBookingSerializer,
    CreateServiceBookingSerializer,
    AvailableSlotSerializer,
    ServiceCategorySerializer
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

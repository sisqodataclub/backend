import logging
from datetime import datetime, timedelta
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import permissions
from django.shortcuts import get_object_or_404
from django.utils import timezone

# ✅ IMPORTED ServiceCategory
from .models import Service, ServiceBooking, ServiceProvider, ServiceCategory
from .serializers import (
    ServiceSerializer,
    ServiceBookingSerializer,
    CreateServiceBookingSerializer,
    AvailableSlotSerializer,
    ServiceCategorySerializer # ✅ IMPORTED
)
from .availability import get_available_slots
from payments.views import create_service_payment_intent

logger = logging.getLogger(__name__)

# ==========================================
# NEW: Category ViewSet
# ==========================================
class ServiceCategoryViewSet(ModelViewSet):
    """Allows frontend to fetch categories (e.g., for navigation tabs)"""
    queryset = ServiceCategory.objects.all()
    serializer_class = ServiceCategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            return ServiceCategory.objects.none()
        # Only return active categories for this specific tenant
        return self.queryset.filter(tenant_id=self.request.tenant.id, is_active=True)

# ==========================================
# UPDATED: Service ViewSet
# ==========================================
class ServiceViewSet(ModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        """✅ SECURE: Tenant-filtered queryset with query params filtering"""
        if not hasattr(self.request, 'tenant') or not self.request.tenant:
            logger.warning("ServiceViewSet accessed without tenant context")
            return Service.objects.none()

        # Start with tenant's active services
        queryset = self.queryset.filter(tenant_id=self.request.tenant.id, is_active=True)

        # ✅ NEW: Allow frontend to filter by category (?category=1)
        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        # ✅ NEW: Filter out addons unless specifically requested
        # (Useful so the main menu doesn't show "Clean Inside Fridge" as a standalone service)
        include_addons = self.request.query_params.get('include_addons')
        if not include_addons or include_addons.lower() == 'false':
            queryset = queryset.filter(is_addon_only=False)

        return queryset

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


class ServiceBookingViewSet(ModelViewSet):
    # ... KEEP THIS EXACTLY THE SAME AS YOUR CURRENT CODE ...
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
        # ... KEEP THIS EXACTLY THE SAME AS YOUR CURRENT CODE ...
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
        # ... KEEP EXACTLY THE SAME ...
        booking = self.get_object()
        if booking.status != 'pending':
            return Response({"error": "Booking cannot be confirmed"}, status=400)
        booking.status = 'confirmed'
        booking.save()
        return Response({"status": "confirmed"})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        # ... KEEP EXACTLY THE SAME ...
        booking = self.get_object()
        if booking.status not in ['pending', 'confirmed']:
            return Response({"error": "Cannot cancel this booking"}, status=400)
        booking.status = 'cancelled'
        booking.save()
        return Response({"status": "cancelled"})

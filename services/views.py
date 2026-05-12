from datetime import datetime, timedelta
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Service, ServiceBooking, ServiceProvider
from .serializers import (
    ServiceSerializer,
    ServiceBookingSerializer,
    CreateServiceBookingSerializer,
    AvailableSlotSerializer
)
from .availability import get_available_slots
from payments.views import create_service_payment_intent


class ServiceViewSet(ModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        # multi-tenant filtering – assume tenant_id is attached by middleware
        return self.queryset.filter(tenant_id=self.request.tenant.id)

    @action(detail=True, methods=['get'])
    def available_slots(self, request, pk=None):
        service = self.get_object()
        date_str = request.query_params.get('date')
        provider_id = request.query_params.get('provider_id')

        if not date_str:
            return Response({"error": "date parameter required"}, status=400)

        try:
            # parse YYYY-MM-DD and make datetime at start of day
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
    serializer_class = ServiceBookingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # staff can see all bookings for the tenant; regular users see only their own
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

        # double-check availability (prevent race conditions)
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

        # create booking with direct customer fields (no Customer model)
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

        # create Stripe PaymentIntent (manual capture)
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

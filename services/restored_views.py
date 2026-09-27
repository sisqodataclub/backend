from datetime import datetime
from rest_framework import generics, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from .models import ServiceBooking
from .serializers import ServiceBookingAnalyticsSerializer


class ServiceBookingAnalyticsView(generics.ListAPIView):
    """
    API endpoint for the analytics dashboard.
    Returns all bookings with all analytical fields, filterable and searchable.
    Supports date range filtering via start_date and end_date query parameters
    (filters on cleaning_booking__created_at).
    """
    serializer_class = ServiceBookingAnalyticsSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        'payment_status',
        'status',
        'has_complaint',
        'rating',
        'utm_source',
        'utm_medium',
    ]
    search_fields = ['customer_name', 'customer_email', 'service__name', 'complaint_notes', 'internal_notes']
    ordering_fields = ['created_at', 'total_price', 'customer_name', 'completed_at', 'payment_date']
    ordering = ['-created_at']

    def get_queryset(self):
        tenant = self.request.tenant
        if not tenant:
            return ServiceBooking.objects.none()
        queryset = ServiceBooking.objects.filter(tenant=tenant).select_related(
            'service', 'provider', 'cleaning_booking'
        )
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d').date()
                queryset = queryset.filter(cleaning_booking__created_at__date__gte=start)
            except ValueError:
                pass
        if end_date:
            try:
                end = datetime.strptime(end_date, '%Y-%m-%d').date()
                queryset = queryset.filter(cleaning_booking__created_at__date__lte=end)
            except ValueError:
                pass
        return queryset


@api_view(['GET'])
@permission_classes([AllowAny])
def get_blocked_times(request):
    """
    Return blocked time ranges for the current tenant.
    """
    from .models import BlockedTime
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return Response({'blocked_times': []})
    qs = BlockedTime.objects.filter(tenant=tenant).order_by('start_time')
    data = [
        {
            'id': bt.id,
            'start_time': bt.start_time.isoformat(),
            'end_time': bt.end_time.isoformat(),
            'reason': getattr(bt, 'reason', ''),
        }
        for bt in qs
    ]
    return Response({'blocked_times': data})

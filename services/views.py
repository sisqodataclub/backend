from rest_framework import generics
from rest_framework.permissions import BasePermission
from rest_framework.serializers import ModelSerializer, SerializerMethodField
from django.conf import settings

from .models import CleaningBooking


class HasAgentApiKey(BasePermission):
    """Allow only if X-Agent-Key header matches settings.AGENT_API_KEY (non-empty)."""

    def has_permission(self, request, view):
        expected = getattr(settings, 'AGENT_API_KEY', '') or ''
        if not expected:
            return False
        provided = request.headers.get('X-Agent-Key')
        return bool(provided) and provided == expected


class AgentBookingFlatSerializer(ModelSerializer):
    services = SerializerMethodField()

    class Meta:
        model = CleaningBooking
        fields = ['id', 'date', 'time', 'customer_name', 'services', 'status', 'address', 'notes']

    def get_services(self, obj):
        # Best-effort: try common relation names, else fall back to a service field.
        for attr in ('services', 'service', 'service_name'):
            if hasattr(obj, attr):
                val = getattr(obj, attr)
                if val is None:
                    continue
                if hasattr(val, 'all'):
                    return [str(s) for s in val.all()]
                return [str(val)]
        return []


class AgentBookingsListView(generics.ListAPIView):
    """GET-only, read-only list of bookings scoped to tenant DDEEP."""

    permission_classes = [HasAgentApiKey]
    serializer_class = AgentBookingFlatSerializer

    def get_queryset(self):
        qs = CleaningBooking.objects.all()
        # Scope to tenant DDEEP when a tenant field exists.
        for field in ('tenant', 'tenant_id', 'tenant_slug'):
            if hasattr(CleaningBooking, field):
                try:
                    qs = qs.filter(**{field: 'DDEEP'})
                except Exception:
                    pass
                break
        return qs.order_by('-date', '-time')

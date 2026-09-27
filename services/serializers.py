from rest_framework import serializers
from .models import (
    Service, ServiceProvider, ServiceBooking, ServiceCategory,
    BookingSnapshot, CleaningBooking
)


# ============================================================
# CATEGORY SERIALIZER
# ============================================================
class ServiceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCategory
        fields = ['id', 'name', 'description', 'image_url', 'display_order', 'is_active']


# ============================================================
# SERVICE SERIALIZER
# ============================================================
class ServiceSerializer(serializers.ModelSerializer):
    category_detail = ServiceCategorySerializer(source='category', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True, default="Uncategorized")

    class Meta:
        model = Service
        fields = '__all__'


# ============================================================
# SERVICE PROVIDER SERIALIZER
# ============================================================
class ServiceProviderSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    service_name = serializers.CharField(source='service.name', read_only=True)

    class Meta:
        model = ServiceProvider
        fields = ['id', 'user', 'user_email', 'service', 'service_name', 'is_active', 'weekly_availability']


# ============================================================
# SERVICE BOOKING SERIALIZER (time‑slot appointments)
# ============================================================
class ServiceBookingSerializer(serializers.ModelSerializer):
    service_detail = ServiceSerializer(source='service', read_only=True)
    provider_detail = ServiceProviderSerializer(source='provider', read_only=True)

    class Meta:
        model = ServiceBooking
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'total_price', 'stripe_payment_intent_id']


# ============================================================
# CREATE SERVICE BOOKING SERIALIZER (validates input)
# ============================================================
class CreateServiceBookingSerializer(serializers.Serializer):
    service_id = serializers.IntegerField()
    provider_id = serializers.IntegerField(required=False, allow_null=True)
    start_time = serializers.DateTimeField()
    customer_email = serializers.EmailField()
    customer_name = serializers.CharField(required=False, allow_blank=True)
    customer_notes = serializers.CharField(required=False, allow_blank=True)


# ============================================================
# AVAILABLE SLOT SERIALIZER
# ============================================================
class AvailableSlotSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    provider_id = serializers.IntegerField(allow_null=True)


# ============================================================
# BOOKING SNAPSHOT SERIALIZER
# ============================================================
class BookingSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingSnapshot
        fields = '__all__'


# ============================================================
# CLEANING BOOKING SERIALIZER
# ============================================================
class CleaningBookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = CleaningBooking
        fields = '__all__'          # ✅ Automatically includes the new 'source' field
        read_only_fields = ['id', 'created_at', 'status']


# ============================================================
# AGENT BOOKING FLAT SERIALIZER (read-only, agent endpoint)
# ============================================================
class AgentBookingFlatSerializer(serializers.ModelSerializer):
    date = serializers.SerializerMethodField()
    time = serializers.SerializerMethodField()
    customer_name = serializers.CharField()
    services = serializers.SerializerMethodField()
    status = serializers.CharField()
    address = serializers.SerializerMethodField()
    notes = serializers.SerializerMethodField()

    class Meta:
        model = CleaningBooking
        fields = ['id', 'date', 'time', 'customer_name', 'services', 'status', 'address', 'notes']

    def _selected_datetime(self, obj):
        return obj.selected_datetime if isinstance(obj.selected_datetime, dict) else {}

    def _property_details(self, obj):
        return obj.property_details if isinstance(obj.property_details, dict) else {}

    def get_date(self, obj):
        return self._selected_datetime(obj).get('booking_date', '') or ''

    def get_time(self, obj):
        return self._selected_datetime(obj).get('timeslot', '') or ''

    def get_address(self, obj):
        details = self._property_details(obj)
        address = details.get('address', '') or ''
        postcode = details.get('postcode', '') or ''
        if postcode:
            return f"{address} {postcode}".strip()
        return address

    def get_notes(self, obj):
        # CleaningBooking has no dedicated notes column.
        return ''

    def get_services(self, obj):
        """Resolve service names from the JSON quantity buckets."""
        all_items = {}
        for bucket in (obj.quantities, obj.carpets, obj.appliances):
            if isinstance(bucket, dict):
                all_items.update(bucket)

        numeric_ids = []
        for key in all_items.keys():
            try:
                numeric_ids.append(int(key))
            except (ValueError, TypeError):
                continue

        names = []
        if numeric_ids:
            services_map = {
                s.id: s.name
                for s in Service.objects.filter(id__in=numeric_ids)
            }
            for sid in numeric_ids:
                name = services_map.get(sid)
                if name:
                    names.append(name)
        return names


# ============================================================
# SERVICE BOOKING ANALYTICS SERIALIZER (restored from 1909695f)
# ============================================================
class ServiceBookingAnalyticsSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source='service.name', read_only=True)
    provider_name = serializers.CharField(source='provider.user.email', read_only=True, default=None)
    cleaning_booking_id = serializers.IntegerField(source='cleaning_booking.id', read_only=True, allow_null=True)

    # Derived from NotificationLog via GenericRelation @property
    last_arrival_sent_at = serializers.DateTimeField(read_only=True)
    last_review_sent_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = ServiceBooking
        fields = [
            'id', 'customer_name', 'customer_email', 'phone',
            'service_name', 'provider_name',
            'start_time', 'end_time',
            'payment_status', 'payment_date', 'payment_reference',
            'status',
            'completed_at',
            'has_complaint', 'complaint_notes', 'complaint_resolved', 'complaint_resolved_at',
            'rating', 'feedback_text',
            'reschedule_history', 'rescheduled_count',
            'discount_applied', 'tax_applied', 'total_price',
            'cancellation_reason',
            'utm_source', 'utm_medium', 'utm_campaign',
            'actual_duration_minutes',
            'internal_notes',
            'created_at', 'updated_at',
            'cleaning_booking_id',
            'last_arrival_sent_at',
            'last_review_sent_at',
        ]

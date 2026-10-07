from rest_framework import serializers
from decimal import Decimal
from .models import (
    Service, ServiceProvider, ServiceBooking, ServiceCategory,
    BookingSnapshot, CleaningBooking
)

# Minimum charge applied to ALL services — any total below this is clamped up.
MINIMUM_CHARGE = Decimal('50.00')


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

    def validate_total(self, value):
        """Clamp the booking total to the £50 minimum for EVERY service."""
        try:
            amount = Decimal(str(value))
        except (TypeError, ValueError):
            amount = Decimal('0.00')
        return max(amount, MINIMUM_CHARGE)

    def validate(self, attrs):
        """Ensure the total is clamped even when it is not part of the payload."""
        attrs = super().validate(attrs)
        current = attrs.get('total', getattr(self.instance, 'total', None))
        if current is not None:
            try:
                amount = Decimal(str(current))
            except (TypeError, ValueError):
                amount = Decimal('0.00')
            attrs['total'] = max(amount, MINIMUM_CHARGE)
        return attrs


# ============================================================
# AGENT BOOKING FLAT SERIALIZER (read-only, agent endpoint)
# ============================================================
class AgentBookingFlatSerializer(serializers.ModelSerializer):
    class Meta:
        model = CleaningBooking
        fields = '__all__'
        read_only_fields = '__all__'
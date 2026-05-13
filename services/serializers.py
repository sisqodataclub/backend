from rest_framework import serializers
from .models import Service, ServiceProvider, ServiceBooking, ServiceCategory

# ✅ NEW: Serializer for the Category model
class ServiceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCategory
        fields = ['id', 'name', 'description', 'image_url', 'display_order', 'is_active']


class ServiceSerializer(serializers.ModelSerializer):
    # ✅ NEW: This embeds the category data (like name and image) right into the Service response
    category_detail = ServiceCategorySerializer(source='category', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True, default="Uncategorized")

    class Meta:
        model = Service
        fields = '__all__'


class ServiceProviderSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    service_name = serializers.CharField(source='service.name', read_only=True)

    class Meta:
        model = ServiceProvider
        fields = ['id', 'user', 'user_email', 'service', 'service_name', 'is_active', 'weekly_availability']


class ServiceBookingSerializer(serializers.ModelSerializer):
    service_detail = ServiceSerializer(source='service', read_only=True)
    provider_detail = ServiceProviderSerializer(source='provider', read_only=True)

    class Meta:
        model = ServiceBooking
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'total_price', 'stripe_payment_intent_id']


class CreateServiceBookingSerializer(serializers.Serializer):
    service_id = serializers.IntegerField()
    provider_id = serializers.IntegerField(required=False, allow_null=True)
    start_time = serializers.DateTimeField()
    customer_email = serializers.EmailField()
    customer_name = serializers.CharField(required=False, allow_blank=True)
    customer_notes = serializers.CharField(required=False, allow_blank=True)


class AvailableSlotSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    provider_id = serializers.IntegerField(allow_null=True)

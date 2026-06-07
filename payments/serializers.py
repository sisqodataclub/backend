"""
Payment Serializers - Handles checkout, bookings, and full invoice management
"""
from rest_framework import serializers
from .models import Booking, BookingItem
from products.models import Product


# ============================================================================
# Existing E-commerce Serializers (unchanged)
# ============================================================================
class CheckoutItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=100)
    variant = serializers.CharField(required=False, allow_blank=True)


class CreateCheckoutSerializer(serializers.Serializer):
    items = CheckoutItemSerializer(many=True)
    customer_email = serializers.EmailField()
    customer_name = serializers.CharField(required=False, allow_blank=True)
    is_gift = serializers.BooleanField(default=False)
    gift_message = serializers.CharField(required=False, allow_blank=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required")
        return value


class BookingItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingItem
        fields = [
            'id', 'product_name', 'product_sku', 'variant_name',
            'unit_price', 'quantity', 'line_total', 'product_image',
        ]


class BookingSerializer(serializers.ModelSerializer):
    items = BookingItemSerializer(many=True, read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id', 'customer_email', 'customer_name', 'status',
            'subtotal', 'shipping_cost', 'total', 'is_gift', 'gift_message',
            'created_at', 'updated_at', 'paid_at', 'items',
        ]
        read_only_fields = [
            'id', 'status', 'subtotal', 'shipping_cost', 'total',
            'created_at', 'updated_at', 'paid_at',
        ]


class CheckoutResponseSerializer(serializers.Serializer):
    checkout_url = serializers.URLField()
    booking_id = serializers.IntegerField()
    session_id = serializers.CharField()


# ============================================================================
# Invoice Serializers (matching django-sage-invoice models)
# ============================================================================

class CategorySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)


class InvoiceItemWriteSerializer(serializers.Serializer):
    """For creating/updating invoice line items – matches sage_invoice.Item model"""
    id = serializers.IntegerField(required=False)
    description = serializers.CharField()
    quantity = serializers.IntegerField(min_value=1)
    measurement = serializers.CharField(required=False, allow_blank=True)  # field name is 'measurement'
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount_rate = serializers.DecimalField(max_digits=5, decimal_places=2, default=0)
    # tax_rate and total are NOT stored on the Item model


class InvoiceItemReadSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    description = serializers.CharField()
    quantity = serializers.IntegerField()
    measurement = serializers.CharField(required=False)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    total_price = serializers.SerializerMethodField()

    def get_total_price(self, obj):
        return obj.quantity * obj.unit_price * (1 - (obj.discount_rate or 0) / 100)


class InvoiceReadSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    invoice_number = serializers.SerializerMethodField()
    title = serializers.CharField()
    slug = serializers.CharField()
    invoice_date = serializers.DateField()
    due_date = serializers.DateField()
    status = serializers.CharField()
    receipt = serializers.BooleanField()
    currency = serializers.CharField()
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    category = CategorySerializer(allow_null=True)
    notes = serializers.CharField()
    logo = serializers.CharField()
    signature = serializers.CharField()
    stamp = serializers.CharField()
    template_choice = serializers.CharField()
    items = InvoiceItemReadSerializer(many=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    customer_name = serializers.CharField()
    contacts = serializers.JSONField()   # expects {"email": "...", "phone": "..."}

    def get_invoice_number(self, obj):
        return f"INV-{obj.id:06d}"


class InvoiceListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    invoice_number = serializers.SerializerMethodField()
    title = serializers.CharField()
    invoice_date = serializers.DateField()
    due_date = serializers.DateField()
    status = serializers.CharField()
    currency = serializers.CharField()
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    customer_name = serializers.CharField()
    contacts = serializers.JSONField()

    def get_invoice_number(self, obj):
        return f"INV-{obj.id:06d}"


# ============================================================================
# React Dashboard Serializers (for create_with_items endpoint)
# ============================================================================

class InvoiceItemPayloadSerializer(serializers.Serializer):
    service_id = serializers.IntegerField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True)
    quantity = serializers.IntegerField(default=1, min_value=1)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)
    discount = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)
    measurement_unit = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        if not data.get('service_id') and not data.get('description'):
            raise serializers.ValidationError("Must provide either a service_id or a description.")
        return data


class InvoiceCreationRequestSerializer(serializers.Serializer):
    """Accepts the full payload from the React frontend"""
    customer_email = serializers.EmailField(required=True)
    customer_name = serializers.CharField(required=False, allow_blank=True)
    customer_phone = serializers.CharField(required=False, allow_blank=True)
    title = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(required=False, default='draft')
    currency = serializers.CharField(required=False, default='USD')
    notes = serializers.CharField(required=False, allow_blank=True)
    template_choice = serializers.CharField(required=False, default='quotation_1')
    invoice_date = serializers.DateField(required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    receipt = serializers.BooleanField(required=False, default=False)
    category = serializers.IntegerField(required=False, allow_null=True)
    items = InvoiceItemPayloadSerializer(many=True, required=True)
    tax_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)
    discount_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)
    concession_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        return value


class ServiceListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    description = serializers.CharField(required=False, allow_blank=True)
    duration_minutes = serializers.IntegerField(required=False)

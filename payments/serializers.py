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

# ============================================================================
# Invoice Serializers (explicit, no apps.get_model, no AppRegistryNotReady)
# ============================================================================

class CategorySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()          # field name is 'title', not 'name'
    description = serializers.CharField(required=False, allow_blank=True)


class ExpenseSerializer(serializers.Serializer):
    """Matches sage_invoice.models.Expense exactly."""
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)
    tax_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    discount_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    concession_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    tax_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    concession_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)


class InvoiceItemReadSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    description = serializers.CharField()
    quantity = serializers.IntegerField(allow_null=True)
    measurement = serializers.CharField(allow_null=True, required=False)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2)


class InvoiceReadSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    invoice_number = serializers.SerializerMethodField()
    title = serializers.CharField()
    slug = serializers.CharField(required=False, allow_blank=True)
    invoice_date = serializers.DateField()
    due_date = serializers.DateField()
    status = serializers.CharField()
    receipt = serializers.BooleanField()
    currency = serializers.CharField()
    customer_name = serializers.CharField()
    contacts = serializers.JSONField()
    category = CategorySerializer(allow_null=True, required=False)
    notes = serializers.JSONField(required=False, allow_null=True)
    logo = serializers.CharField(required=False, allow_null=True)
    signature = serializers.CharField(required=False, allow_null=True)
    stamp = serializers.CharField(required=False, allow_null=True)
    template_choice = serializers.CharField()
    items = InvoiceItemReadSerializer(many=True)
    expense = ExpenseSerializer(required=False, allow_null=True)
    created_at = serializers.DateTimeField(required=False)
    updated_at = serializers.DateTimeField(required=False)

    def get_invoice_number(self, obj):
        obj_id = getattr(obj, 'id', obj.get('id') if isinstance(obj, dict) else 0)
        return f"INV-{obj_id:06d}"


# ----------------------------------------------------------------------
# Payload serializers for the React frontend (create_with_items)
# ----------------------------------------------------------------------
class InvoiceItemPayloadSerializer(serializers.Serializer):
    service_id = serializers.IntegerField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True)
    quantity = serializers.IntegerField(default=1, min_value=1)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)
    discount = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)
    measurement = serializers.CharField(required=False, allow_blank=True)   # matches sage_invoice field name

    def validate(self, data):
        if not data.get('service_id') and not data.get('description'):
            raise serializers.ValidationError("Must provide either a service_id or a description.")
        return data


class InvoiceCreationRequestSerializer(serializers.Serializer):
    """Accepts React's payload (issue_date, measurement_unit, etc.) and maps correctly."""
    customer_email = serializers.EmailField(required=True)
    customer_name = serializers.CharField(required=False, allow_blank=True)
    customer_phone = serializers.CharField(required=False, allow_blank=True)
    title = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(required=False, default='draft')
    currency = serializers.CharField(required=False, default='USD')
    notes = serializers.CharField(required=False, allow_blank=True)
    template_choice = serializers.CharField(required=False, default='quotation_1')
    issue_date = serializers.DateField(required=False, allow_null=True)   # React sends issue_date
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

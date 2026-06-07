"""
Payment Serializers
Handles checkout requests, booking responses, and invoices (without model imports)
"""
from rest_framework import serializers
from .models import Booking, BookingItem
from products.models import Product


# ============================================================================
# Existing E-commerce Serializers (unchanged)
# ============================================================================
class CheckoutItemSerializer(serializers.Serializer):
    """
    Serializer for items in checkout request
    Frontend sends only product_id and quantity (NOT prices)
    """
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=100)
    variant = serializers.CharField(required=False, allow_blank=True)


class CreateCheckoutSerializer(serializers.Serializer):
    """
    Serializer for creating a checkout session
    Frontend sends items and customer info (NOT prices)
    """
    items = CheckoutItemSerializer(many=True)
    customer_email = serializers.EmailField()
    customer_name = serializers.CharField(required=False, allow_blank=True)
    is_gift = serializers.BooleanField(default=False)
    gift_message = serializers.CharField(required=False, allow_blank=True)

    def validate_items(self, value):
        """Ensure at least one item"""
        if not value:
            raise serializers.ValidationError("At least one item is required")
        return value


class BookingItemSerializer(serializers.ModelSerializer):
    """Serializer for booking items"""

    class Meta:
        model = BookingItem
        fields = [
            'id',
            'product_name',
            'product_sku',
            'variant_name',
            'unit_price',
            'quantity',
            'line_total',
            'product_image',
        ]


class BookingSerializer(serializers.ModelSerializer):
    """Serializer for booking/order details"""
    items = BookingItemSerializer(many=True, read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id',
            'customer_email',
            'customer_name',
            'status',
            'subtotal',
            'shipping_cost',
            'total',
            'is_gift',
            'gift_message',
            'created_at',
            'updated_at',
            'paid_at',
            'items',
        ]
        read_only_fields = [
            'id',
            'status',
            'subtotal',
            'shipping_cost',
            'total',
            'created_at',
            'updated_at',
            'paid_at',
        ]


class CheckoutResponseSerializer(serializers.Serializer):
    """Response after creating checkout session"""
    checkout_url = serializers.URLField()
    booking_id = serializers.IntegerField()
    session_id = serializers.CharField()


# ============================================================================
# Invoice-related Serializers (no direct model imports)
# ============================================================================

class InvoiceCreationRequestSerializer(serializers.Serializer):
    """
    Validates incoming request to create an invoice from service selections.
    Does not import any sage_invoice models.
    """
    customer_email = serializers.EmailField()
    customer_name = serializers.CharField(required=False, allow_blank=True)
    issue_date = serializers.DateField(required=False)
    due_date = serializers.DateField(required=False)
    items = serializers.ListField(
        child=serializers.DictField(),
        required=True
    )

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        for idx, item in enumerate(value):
            # Each item must have either service_id or description
            if 'service_id' not in item and not item.get('description'):
                raise serializers.ValidationError(
                    f"Item {idx}: must provide either service_id or description"
                )
            if item.get('quantity', 0) <= 0:
                raise serializers.ValidationError(
                    f"Item {idx}: quantity must be positive"
                )
        return value


class InvoiceItemSerializer(serializers.Serializer):
    """Read-only representation of invoice items (for API responses)"""
    id = serializers.IntegerField()
    description = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    total = serializers.DecimalField(max_digits=10, decimal_places=2)


class CustomerProfileSerializer(serializers.Serializer):
    """Read-only customer info from sage_invoice"""
    id = serializers.IntegerField()
    name = serializers.CharField(allow_blank=True)
    email = serializers.EmailField()
    phone = serializers.CharField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)


class InvoiceSerializer(serializers.Serializer):
    """Read-only invoice representation (matches sage_invoice.Invoice)"""
    id = serializers.IntegerField()
    invoice_number = serializers.CharField()
    status = serializers.CharField()
    issue_date = serializers.DateField()
    due_date = serializers.DateField()
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    created_at = serializers.DateTimeField()
    customer_detail = CustomerProfileSerializer(source='customer', read_only=True)
    items = InvoiceItemSerializer(many=True, read_only=True)


class ServiceListSerializer(serializers.Serializer):
    """Serializer for listing services (used in ServiceViewSet)"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    description = serializers.CharField(required=False, allow_blank=True)

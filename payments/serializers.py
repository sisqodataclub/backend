"""
Payment Serializers
Handles checkout requests, booking responses, and full invoice management
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
# Invoice Full Serializers (Read & Write)
# ============================================================================

class CategorySerializer(serializers.Serializer):
    """Category reference for invoices"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)


class CustomerProfileDetailSerializer(serializers.Serializer):
    """Detailed customer info for invoice (read-only)"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)


class InvoiceItemWriteSerializer(serializers.Serializer):
    """Serializer for creating/updating invoice line items directly"""
    id = serializers.IntegerField(required=False)          # for updates
    description = serializers.CharField()
    quantity = serializers.IntegerField(min_value=1)
    measurement_unit = serializers.CharField(required=False, allow_blank=True)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_rate = serializers.DecimalField(max_digits=5, decimal_places=2, default=0)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)


class InvoiceItemReadSerializer(serializers.Serializer):
    """Read-only representation of invoice items"""
    id = serializers.IntegerField()
    description = serializers.CharField()
    quantity = serializers.IntegerField()
    measurement_unit = serializers.CharField(required=False)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    discount_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    total = serializers.DecimalField(max_digits=10, decimal_places=2)


class InvoiceWriteSerializer(serializers.Serializer):
    """
    Full invoice serializer for create/update operations.
    All fields are optional for updates.
    """
    title = serializers.CharField(required=False, allow_blank=True)
    slug = serializers.CharField(required=False, allow_blank=True)
    invoice_number = serializers.CharField(required=False, allow_blank=True)
    tracking_code = serializers.CharField(required=False, allow_blank=True)
    issue_date = serializers.DateField(required=False)
    due_date = serializers.DateField(required=False)
    customer = serializers.IntegerField(required=False)          
    status = serializers.ChoiceField(choices=['draft', 'sent', 'paid', 'overdue', 'cancelled'], required=False)
    is_receipt = serializers.BooleanField(required=False, default=False)
    currency = serializers.CharField(required=False, default='USD')
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, read_only=True)
    category = serializers.IntegerField(required=False, allow_null=True)   
    notes = serializers.CharField(required=False, allow_blank=True)
    logo = serializers.ImageField(required=False, allow_null=True)
    signature = serializers.ImageField(required=False, allow_null=True)
    stamp = serializers.ImageField(required=False, allow_null=True)
    template_choice = serializers.CharField(required=False, allow_blank=True)
    items = InvoiceItemWriteSerializer(many=True, required=False)
    tax_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)
    discount_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)
    concession_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)


class InvoiceReadSerializer(serializers.Serializer):
    """Full invoice representation for API responses"""
    id = serializers.IntegerField()
    invoice_number = serializers.CharField()
    title = serializers.CharField(required=False)
    slug = serializers.CharField(required=False)
    tracking_code = serializers.CharField(required=False)
    issue_date = serializers.DateField()
    due_date = serializers.DateField()
    status = serializers.CharField()
    is_receipt = serializers.BooleanField()
    currency = serializers.CharField()
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    category = CategorySerializer(required=False, allow_null=True)
    notes = serializers.CharField(required=False)
    logo = serializers.CharField(required=False)       
    signature = serializers.CharField(required=False) 
    stamp = serializers.CharField(required=False)     
    template_choice = serializers.CharField(required=False)
    customer_detail = CustomerProfileDetailSerializer(source='customer', read_only=True)
    items = InvoiceItemReadSerializer(many=True, read_only=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class InvoiceListSerializer(serializers.Serializer):
    """Lightweight serializer for invoice list view (with filters)"""
    id = serializers.IntegerField()
    invoice_number = serializers.CharField()
    title = serializers.CharField(required=False)
    issue_date = serializers.DateField()
    due_date = serializers.DateField()
    status = serializers.CharField()
    currency = serializers.CharField()
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    customer_email = serializers.EmailField(source='customer.email', read_only=True)


# ============================================================================
# React Dashboard Serializers (The Mega Form)
# ============================================================================

class InvoiceItemPayloadSerializer(serializers.Serializer):
    """Validates individual items coming from the React Mega Form"""
    service_id = serializers.IntegerField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True)
    quantity = serializers.IntegerField(default=1, min_value=1)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)
    discount = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)

    def validate(self, data):
        # Must provide either a service_id or a manual description
        if not data.get('service_id') and not data.get('description'):
            raise serializers.ValidationError("Must provide either a service_id or a description.")
        return data


class InvoiceCreationRequestSerializer(serializers.Serializer):
    """
    Validates incoming request to create an invoice from the React dashboard.
    Accepts the full suite of fields generated by the new frontend UI.
    """
    customer_email = serializers.EmailField()
    customer_name = serializers.CharField(required=False, allow_blank=True)
    title = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(required=False, default='draft')
    currency = serializers.CharField(required=False, default='USD')
    notes = serializers.CharField(required=False, allow_blank=True)
    template_choice = serializers.CharField(required=False, default='quotation_1')
    issue_date = serializers.DateField(required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    
    items = InvoiceItemPayloadSerializer(many=True, required=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        return value


class ServiceListSerializer(serializers.Serializer):
    """Serializer for listing services (used in ServiceViewSet)"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    description = serializers.CharField(required=False, allow_blank=True)

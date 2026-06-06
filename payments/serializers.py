"""
Payment Serializers
Handles checkout requests and booking responses
"""
from rest_framework import serializers
from .models import Booking, BookingItem
from products.models import Product


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





# payments/serializers.py (add these)
from sage_invoice.models import Customer, Invoice, InvoiceItem
from services.models import Service  # adjust if your Service model is elsewhere

class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ['id', 'name', 'price', 'description']

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['id', 'name', 'email', 'phone', 'address']

class InvoiceItemSerializer(serializers.ModelSerializer):
    service_id = serializers.IntegerField(write_only=True, required=False)
    service_name = serializers.CharField(source='description', read_only=True)

    class Meta:
        model = InvoiceItem
        fields = ['id', 'description', 'quantity', 'unit_price', 'tax_rate', 'total', 'service_id', 'service_name']
        read_only_fields = ['total']

class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    customer_detail = CustomerSerializer(source='customer', read_only=True)

    class Meta:
        model = Invoice
        fields = ['id', 'invoice_number', 'customer', 'customer_detail', 'status',
                  'issue_date', 'due_date', 'total_amount', 'items', 'created_at']

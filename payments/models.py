"""
Payment and Booking Models with Tenant Support
Secure payment processing with Stripe integration
"""
from django.db import models
from django.utils import timezone
from core.models import TenantAwareModel
from products.models import Product


class Booking(TenantAwareModel):
    """
    Booking/Order Model - Source of truth for purchases
    Tenant-aware with automatic filtering
    """
    
    STATUS_CHOICES = [
        ('UNPAID', 'Unpaid - Awaiting Payment'),
        ('PENDING', 'Pending - Payment Processing'),
        ('PAID', 'Paid - Payment Successful'),
        ('FAILED', 'Failed - Payment Failed'),
        ('REFUNDED', 'Refunded'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    # Customer Information
    customer_email = models.EmailField()
    customer_name = models.CharField(max_length=200, blank=True)
    
    # Booking Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='UNPAID',
        db_index=True
    )
    
    # Pricing (Backend-calculated, immutable after creation)
    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Sum of all items before shipping"
    )
    shipping_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00
    )
    total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Final total amount charged"
    )
    
    # Gift Options
    is_gift = models.BooleanField(default=False)
    gift_message = models.TextField(blank=True)
    
    # Stripe Integration
    stripe_checkout_session_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Stripe Checkout Session ID"
    )
    stripe_payment_intent_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Stripe Payment Intent ID"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    notes = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'customer_email']),
            models.Index(fields=['tenant', 'created_at']),
        ]
        verbose_name = 'Booking'
        verbose_name_plural = 'Bookings'
    
    def __str__(self):
        return f"Booking #{self.id} - {self.customer_email} - {self.status}"
    
    def mark_as_paid(self):
        """Mark booking as paid and record timestamp"""
        self.status = 'PAID'
        self.paid_at = timezone.now()
        self.save(update_fields=['status', 'paid_at', 'updated_at'])
    
    def mark_as_failed(self):
        """Mark booking as failed"""
        self.status = 'FAILED'
        self.save(update_fields=['status', 'updated_at'])


class BookingItem(TenantAwareModel):
    """
    Individual items in a booking
    Stores snapshot of product details at time of purchase
    """
    
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Reference to product (may be deleted later)"
    )
    
    # Snapshot of product details at purchase time
    product_name = models.CharField(max_length=200)
    product_sku = models.CharField(max_length=100, blank=True)
    variant_name = models.CharField(max_length=200, blank=True)
    
    # Pricing snapshot (immutable)
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Price per unit at time of purchase"
    )
    quantity = models.PositiveIntegerField(default=1)
    line_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="unit_price * quantity"
    )
    
    # Product image snapshot
    product_image = models.URLField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['id']
        indexes = [
            models.Index(fields=['tenant', 'booking']),
            models.Index(fields=['tenant', 'product']),
        ]
        verbose_name = 'Booking Item'
        verbose_name_plural = 'Booking Items'
    
    def __str__(self):
        return f"{self.product_name} x{self.quantity}"
    
    def save(self, *args, **kwargs):
        """Auto-calculate line total"""
        self.line_total = self.unit_price * self.quantity
        super().save(*args, **kwargs)

from datetime import timedelta
from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from products.models import Product

User = get_user_model()


class Service(Product):
    """
    Extends the existing Product model for time-based services.
    Uses multi-table inheritance.
    """
    # Time attributes
    duration_minutes = models.PositiveIntegerField(help_text="How long the service takes")
    buffer_before = models.PositiveIntegerField(default=0, help_text="Preparation time after booking")
    buffer_after = models.PositiveIntegerField(default=0, help_text="Cleanup time after service")
    max_clients_per_slot = models.PositiveIntegerField(default=1)

    # Staff / provider
    requires_assigned_staff = models.BooleanField(default=True)
    any_staff_can_serve = models.BooleanField(default=True)  # if True, auto-assign

    # Pricing model
    price_fixed = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    price_per_hour = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    # Location
    is_remote = models.BooleanField(default=False)
    address_required = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Service"
        verbose_name_plural = "Services"

    def clean(self):
        if not self.price_fixed and not self.price_per_hour:
            raise ValidationError("Either fixed price or hourly price must be set")
        if self.price_fixed and self.price_per_hour:
            raise ValidationError("Cannot set both fixed and hourly price")

    def calculate_price(self, duration_minutes=None):
        if self.price_fixed:
            return self.price_fixed
        if self.price_per_hour:
            hours = (duration_minutes or self.duration_minutes) / 60
            return self.price_per_hour * hours
        return 0

    def __str__(self):
        return self.name


class ServiceProvider(models.Model):
    """Stores which staff members can provide which services."""
    tenant = models.ForeignKey('core.Tenant', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='service_provider')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='providers')
    is_active = models.BooleanField(default=True)

    # Weekly schedule stored as JSON: {"0": [{"start":"09:00","end":"17:00"}], ...}
    weekly_availability = models.JSONField(default=dict, help_text="Day 0-6 -> list of time slots")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'user', 'service'], name='unique_provider')
        ]

    def __str__(self):
        return f"{self.user.email} - {self.service.name}"


class ServiceBooking(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending payment'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ]

    tenant = models.ForeignKey('core.Tenant', on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.PROTECT)
    provider = models.ForeignKey(ServiceProvider, on_delete=models.SET_NULL, null=True, blank=True)

    # Customer info (direct fields, like e-commerce Booking)
    customer_email = models.EmailField()
    customer_name = models.CharField(max_length=200, blank=True)

    # Booking times
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    # Status & pricing
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    # Stripe
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)

    # Notes
    customer_notes = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['tenant', 'start_time']),
            models.Index(fields=['customer_email', 'status']),
        ]

    def clean(self):
        if self.start_time >= self.end_time:
            raise ValidationError("End time must be after start time")
        expected_end = self.start_time + timedelta(minutes=self.service.duration_minutes)
        if self.end_time != expected_end:
            raise ValidationError(f"End time must be {expected_end} for this service duration")

    def save(self, *args, **kwargs):
        if not self.total_price:
            duration = (self.end_time - self.start_time).total_seconds() / 60
            self.total_price = self.service.calculate_price(duration)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"ServiceBooking #{self.id} - {self.service.name} for {self.customer_email}"

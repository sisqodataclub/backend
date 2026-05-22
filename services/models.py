from datetime import timedelta
from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()


# ==========================================
# NEW: Service Category Model
# ==========================================
class ServiceCategory(models.Model):
    tenant = models.ForeignKey('core.Tenant', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True, help_text="Category cover image")
    display_order = models.PositiveIntegerField(default=0, help_text="Order in which it appears on the frontend")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Service Category"
        verbose_name_plural = "Service Categories"
        ordering = ['display_order', 'name']
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'name'], name='unique_tenant_category')
        ]

    def __str__(self):
        return self.name


# ==========================================
# UPDATED: Service Model (with category, ordering, addon flag)
# ==========================================
class Service(models.Model):
    tenant = models.ForeignKey('core.Tenant', on_delete=models.CASCADE)

    # NEW: Link to Category
    category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='services'
    )

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    # NEW: Display & Logic fields
    display_order = models.PositiveIntegerField(default=0)
    is_addon_only = models.BooleanField(
        default=False,
        help_text="If True, cannot be booked alone (e.g., 'Inside Fridge')"
    )

    # Time attributes
    duration_minutes = models.PositiveIntegerField(help_text="How long the service takes")
    buffer_before = models.PositiveIntegerField(default=0, help_text="Preparation time after booking")
    buffer_after = models.PositiveIntegerField(default=0, help_text="Cleanup time after service")
    max_clients_per_slot = models.PositiveIntegerField(default=1)

    # Staff assignment
    requires_assigned_staff = models.BooleanField(default=True)
    any_staff_can_serve = models.BooleanField(default=True)

    # Pricing
    price_fixed = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    price_per_hour = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    # Location
    is_remote = models.BooleanField(default=False)
    address_required = models.BooleanField(default=False)

    # Optional image
    image_url = models.URLField(blank=True, help_text="Service image")

    class Meta:
        verbose_name = "Service"
        verbose_name_plural = "Services"
        ordering = ['category__display_order', 'display_order', 'name']

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
        cat_prefix = f"[{self.category.name}] " if self.category else ""
        return f"{cat_prefix}{self.name}"


# ==========================================
# ServiceProvider (unchanged)
# ==========================================
class ServiceProvider(models.Model):
    tenant = models.ForeignKey('core.Tenant', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='service_provider')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='providers')
    is_active = models.BooleanField(default=True)
    weekly_availability = models.JSONField(default=dict, help_text="Day 0-6 -> list of time slots")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'user', 'service'], name='unique_provider')
        ]

    def __str__(self):
        return f"{self.user.email} - {self.service.name}"


# ==========================================
# ServiceBooking (unchanged)
# ==========================================
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

    customer_email = models.EmailField()
    customer_name = models.CharField(max_length=200, blank=True)

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
    customer_notes = models.TextField(blank=True)

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



# ==========================================
# NEW: Cleaning Booking (Old wizard style)
# ==========================================
class BookingSnapshot(models.Model):
    tenant = models.ForeignKey('core.Tenant', on_delete=models.CASCADE)
    session_id = models.CharField(max_length=100, db_index=True)
    data = models.JSONField(default=dict)
    is_final = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('tenant', 'session_id')]

    def __str__(self):
        return f"Snapshot {self.session_id}"



class CleaningBooking(models.Model):
    tenant = models.ForeignKey('core.Tenant', on_delete=models.CASCADE)
    session_id = models.CharField(max_length=100, unique=True, db_index=True)
    customer_name = models.CharField(max_length=200)
    customer_email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    selected_areas = models.JSONField(default=list)
    quantities = models.JSONField(default=dict)
    carpets = models.JSONField(default=dict)
    appliances = models.JSONField(default=dict)
    furnished_status = models.CharField(max_length=50, blank=True)
    parking = models.CharField(max_length=50, blank=True)
    biohazard = models.CharField(max_length=50, blank=True)
    payment_method = models.CharField(max_length=50)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    paymentlink = models.URLField(blank=True)
    status = models.CharField(max_length=20, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # ✅ NEW: Flexible JSON store for address, postcode, and future location info
    property_details = models.JSONField(default=dict, blank=True)


   # ✅ NEW: Flexible JSON store for scheduling
    selected_datetime = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"CleaningBooking {self.session_id}"




class BlockedTime(models.Model):
    date = models.DateField(db_index=True)
    timeslot = models.CharField(
        max_length=50, 
        blank=True, 
        help_text="Leave blank to block the entire day. Otherwise, type the exact slot to block (e.g., '09:00 - 12:00')."
    )
    reason = models.CharField(max_length=200, blank=True, help_text="e.g., Bank Holiday, Fully Booked, etc.")

    class Meta:
        ordering = ['date']
        unique_together = ('date', 'timeslot')

    def __str__(self):
        if self.timeslot:
            return f"{self.date} | Blocked: {self.timeslot} ({self.reason})"
        return f"{self.date} | Blocked: Entire Day ({self.reason})"





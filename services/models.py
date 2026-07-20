from datetime import timedelta
from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.fields import GenericRelation
from customer_notifications.models import NotificationLog

User = get_user_model()


# ==========================================
# Service Category Model
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
# Service Model
# ==========================================
class Service(models.Model):
    tenant = models.ForeignKey('core.Tenant', on_delete=models.CASCADE)
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
    display_order = models.PositiveIntegerField(default=0)
    is_addon_only = models.BooleanField(
        default=False,
        help_text="If True, cannot be booked alone (e.g., 'Inside Fridge')"
    )
    duration_minutes = models.PositiveIntegerField(help_text="How long the service takes")
    buffer_before = models.PositiveIntegerField(default=0, help_text="Preparation time after booking")
    buffer_after = models.PositiveIntegerField(default=0, help_text="Cleanup time after service")
    max_clients_per_slot = models.PositiveIntegerField(default=1)
    requires_assigned_staff = models.BooleanField(default=True)
    any_staff_can_serve = models.BooleanField(default=True)
    price_fixed = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    price_per_hour = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    is_remote = models.BooleanField(default=False)
    address_required = models.BooleanField(default=False)
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
# ServiceProvider Model
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
# CleaningBooking – master booking record
# ==========================================
class CleaningBooking(models.Model):
    # --- Booking Source Choices ---
    SOURCE_CHOICES = [
        ('website', 'Website'),
        ('sms', 'SMS'),
        ('call', 'Phone Call'),
        ('whatsapp', 'WhatsApp'),
        ('instagram_dm', 'Instagram DM'),
        ('email', 'Email'),
        ('other', 'Other'),
    ]

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
    property_details = models.JSONField(default=dict, blank=True)
    selected_datetime = models.JSONField(default=dict, blank=True)

    # 👇 NEW: Optional source field
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        blank=True,
        null=True,
        help_text="How the booking was received (e.g., website, WhatsApp, etc.)"
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"CleaningBooking {self.session_id}"


# ==========================================
# Enhanced ServiceBooking (linked to CleaningBooking)
# ==========================================
class ServiceBooking(models.Model):
    # --- Link to the master cleaning booking ---
    cleaning_booking = models.ForeignKey(
        CleaningBooking,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='service_bookings',
        help_text="Reference to the original cleaning booking (wizard data)"
    )

    # --- Denormalised customer info (for performance) ---
    customer_email = models.EmailField()
    customer_name = models.CharField(max_length=200, blank=True)

    # --- Additional fields copied from CleaningBooking ---
    phone = models.CharField(max_length=20, blank=True, help_text="Customer phone number")
    property_details = models.JSONField(default=dict, blank=True, help_text="Address, postcode, etc.")
    selected_datetime = models.JSONField(default=dict, blank=True, help_text="Raw booking date and time slot")

    # --- Service & provider ---
    tenant = models.ForeignKey('core.Tenant', on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.PROTECT)
    provider = models.ForeignKey(ServiceProvider, on_delete=models.SET_NULL, null=True, blank=True)

    # --- Scheduling (now optional) ---
    start_time = models.DateTimeField(null=True, blank=True, help_text="Start time of the booking")
    end_time = models.DateTimeField(null=True, blank=True, help_text="End time of the booking")

    # --- Job status ---
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending payment'),
            ('confirmed', 'Confirmed'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
            ('no_show', 'No Show'),
        ],
        default='pending'
    )

    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
    customer_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- ANALYTICAL FIELDS ---

    # Payment tracking
    PAYMENT_STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('paid_cash', 'Paid (Cash)'),
        ('paid_card', 'Paid (Card)'),
        ('paid_bank', 'Paid (Bank Transfer)'),
    ]
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='unpaid',
        db_index=True,
    )
    payment_date = models.DateTimeField(null=True, blank=True, help_text="Date and time payment was received")
    payment_reference = models.CharField(max_length=255, blank=True, help_text="Stripe transaction ID or reference")

    # Job completion
    completed_at = models.DateTimeField(null=True, blank=True, help_text="Date and time the job was marked as completed")

    # Complaint tracking
    has_complaint = models.BooleanField(default=False)
    complaint_notes = models.TextField(blank=True)
    complaint_resolved = models.BooleanField(default=False)
    complaint_resolved_at = models.DateTimeField(null=True, blank=True)

    # Customer feedback
    rating = models.PositiveSmallIntegerField(
        null=True, blank=True,
        choices=[(i, f"{i} Star{'s' if i > 1 else ''}") for i in range(1, 6)],
        help_text="1-5 star rating from customer"
    )
    feedback_text = models.TextField(blank=True)

    # 👇 REMOVED: review_request_sent and review_requested_at – now tracked via GFK

    # Scheduling & rescheduling
    reschedule_history = models.JSONField(default=list, blank=True, help_text="List of {from, to, reason} objects")
    rescheduled_count = models.PositiveIntegerField(default=0, help_text="Number of times the booking was rescheduled")

    # Financial breakdown
    discount_applied = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_applied = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Cancellation
    cancellation_reason = models.TextField(blank=True)

    # Marketing attribution
    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=100, blank=True)

    # Actual job duration
    actual_duration_minutes = models.PositiveIntegerField(null=True, blank=True, help_text="Actual time spent on the job")

    # Internal notes (admin only)
    internal_notes = models.TextField(blank=True, help_text="Private admin notes")

    # --- Reverse link to NotificationLog via GenericForeignKey ---
    notifications = GenericRelation(NotificationLog)

    class Meta:
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['tenant', 'start_time']),
            models.Index(fields=['customer_email', 'status']),
            models.Index(fields=['payment_status', 'payment_date']),
            models.Index(fields=['status', 'completed_at']),
            models.Index(fields=['has_complaint']),
            models.Index(fields=['rating']),
            models.Index(fields=['utm_source', 'utm_medium']),
        ]

    def clean(self):
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError("End time must be after start time")
            if self.service and self.service.duration_minutes:
                expected_end = self.start_time + timedelta(minutes=self.service.duration_minutes)
                if self.end_time != expected_end:
                    raise ValidationError(f"End time must be {expected_end} for this service duration")

    def save(self, *args, **kwargs):
        if not self.total_price and self.start_time and self.end_time and self.service:
            duration = (self.end_time - self.start_time).total_seconds() / 60
            self.total_price = self.service.calculate_price(duration)
        super().save(*args, **kwargs)

    # --- 🧩 Properties to fetch latest notification timestamps ---
    @property
    def last_arrival_sent_at(self):
        latest = self.notifications.filter(notification_type='arrival', is_success=True).first()
        return latest.sent_at if latest else None

    @property
    def last_review_sent_at(self):
        latest = self.notifications.filter(notification_type='review', is_success=True).first()
        return latest.sent_at if latest else None

    def __str__(self):
        return f"ServiceBooking #{self.id} - {self.service.name} for {self.customer_email}"


# ==========================================
# BookingSnapshot (auto-save wizard data)
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


# ==========================================
# BlockedTime (for calendar blocking)
# ==========================================
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

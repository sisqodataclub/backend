# services/admin.py
from django.contrib import admin
from .models import (
    Service, ServiceProvider, ServiceBooking, ServiceCategory,
    BookingSnapshot, CleaningBooking, BlockedTime
)


# ==========================================
# Service Category Admin
# ==========================================
@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'display_order', 'is_active')
    list_filter = ('tenant', 'is_active')
    search_fields = ('name',)
    ordering = ('tenant', 'display_order', 'name')


# ==========================================
# Service Admin
# ==========================================
@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'tenant', 'price_fixed', 'price_per_hour', 'display_order', 'is_addon_only', 'is_active')
    list_filter = ('tenant', 'is_active', 'is_addon_only', 'category', 'requires_assigned_staff')
    search_fields = ('name', 'category__name')
    ordering = ('tenant', 'category__display_order', 'display_order', 'name')


# ==========================================
# Service Provider Admin
# ==========================================
@admin.register(ServiceProvider)
class ServiceProviderAdmin(admin.ModelAdmin):
    list_display = ('user', 'service', 'tenant', 'is_active')
    list_filter = ('tenant', 'is_active')
    search_fields = ('user__email', 'service__name')


# ==========================================
# ENHANCED Service Booking Admin (with analytics fields)
# ==========================================
@admin.register(ServiceBooking)
class ServiceBookingAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'customer_name', 'customer_email',
        'service', 'start_time',
        'payment_status', 'status',  # job status
        'total_price', 'rating', 'has_complaint'
    )
    list_filter = (
        'tenant', 'status', 'payment_status',
        'has_complaint', 'complaint_resolved',
        'rating', 'review_request_sent',
        'utm_source', 'utm_medium',
        'start_time', 'completed_at'
    )
    search_fields = (
        'customer_name', 'customer_email', 'phone',
        'service__name', 'internal_notes', 'complaint_notes'
    )
    readonly_fields = (
        'id', 'created_at', 'updated_at',
        'stripe_payment_intent_id',
        'payment_reference', 'reschedule_history',
        'rescheduled_count'
    )
    fieldsets = (
        ('Customer Information', {
            'fields': ('tenant', 'customer_name', 'customer_email', 'phone')
        }),
        ('Service & Provider', {
            'fields': ('service', 'provider', 'start_time', 'end_time')
        }),
        ('Job Status & Completion', {
            'fields': ('status', 'completed_at', 'actual_duration_minutes', 'customer_notes')
        }),
        ('Payment Details', {
            'fields': ('payment_status', 'payment_date', 'payment_reference', 'total_price', 'discount_applied', 'tax_applied')
        }),
        ('Complaint Tracking', {
            'fields': ('has_complaint', 'complaint_notes', 'complaint_resolved', 'complaint_resolved_at')
        }),
        ('Customer Feedback', {
            'fields': ('rating', 'feedback_text', 'review_request_sent', 'review_requested_at')
        }),
        ('Rescheduling', {
            'fields': ('reschedule_history', 'rescheduled_count')
        }),
        ('Marketing Attribution', {
            'fields': ('utm_source', 'utm_medium', 'utm_campaign')
        }),
        ('Cancellation', {
            'fields': ('cancellation_reason',)
        }),
        ('Internal Notes', {
            'fields': ('internal_notes',)
        }),
        ('System Fields', {
            'fields': ('id', 'created_at', 'updated_at', 'stripe_payment_intent_id'),
            'classes': ('collapse',)
        }),
    )
    ordering = ('-start_time',)


# ==========================================
# NEW: Booking Snapshot Admin (auto‑save wizard data)
# ==========================================
@admin.register(BookingSnapshot)
class BookingSnapshotAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'tenant', 'is_final', 'created_at', 'updated_at')
    list_filter = ('tenant', 'is_final', 'created_at')
    search_fields = ('session_id', 'data')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        ('Snapshot Info', {
            'fields': ('session_id', 'tenant', 'is_final')
        }),
        ('Stored Data', {
            'fields': ('data',),
            'classes': ('wide',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# ==========================================
# Cleaning Booking Admin (old‑style cleaning orders)
# ==========================================
@admin.register(CleaningBooking)
class CleaningBookingAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'customer_name', 'customer_email', 'total', 'payment_method', 'status', 'created_at')
    list_filter = ('tenant', 'payment_method', 'status', 'created_at')
    search_fields = ('session_id', 'customer_name', 'customer_email', 'phone')
    readonly_fields = ('id', 'created_at')
    fieldsets = (
        ('Booking Information', {
            'fields': ('session_id', 'tenant', 'status')
        }),
        ('Customer Details', {
            'fields': ('customer_name', 'customer_email', 'phone')
        }),
        ('Selected Services', {
            'fields': ('selected_areas', 'quantities', 'carpets', 'appliances'),
            'classes': ('wide',)
        }),
        ('Property & Payment', {
            'fields': ('furnished_status', 'parking', 'biohazard', 'payment_method', 'total', 'paymentlink')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


# ==========================================
# BlockedTime Admin
# ==========================================
@admin.register(BlockedTime)
class BlockedTimeAdmin(admin.ModelAdmin):
    list_display = ('date', 'timeslot', 'reason')
    list_filter = ('date',)
    search_fields = ('reason', 'timeslot')

# services/admin.py
from django.contrib import admin
from .models import (
    Service, ServiceProvider, ServiceBooking, ServiceCategory,
    BookingSnapshot, CleaningBooking, BlockedTime  # 👈 new models
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
# Service Booking Admin (time‑slot based)
# ==========================================
@admin.register(ServiceBooking)
class ServiceBookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'service', 'tenant', 'customer_email', 'start_time', 'status', 'total_price')
    list_filter = ('tenant', 'status', 'start_time')
    search_fields = ('customer_email', 'customer_name', 'service__name')
    readonly_fields = ('id', 'created_at', 'updated_at', 'stripe_payment_intent_id')
    fieldsets = (
        ('Customer', {
            'fields': ('customer_email', 'customer_name')
        }),
        ('Service Details', {
            'fields': ('service', 'provider', 'start_time', 'end_time')
        }),
        ('Booking Info', {
            'fields': ('status', 'total_price', 'stripe_payment_intent_id', 'customer_notes')
        }),
        ('Tenant & Timestamps', {
            'fields': ('tenant', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


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
# NEW: Cleaning Booking Admin (old‑style cleaning orders)
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




# (Your existing CleaningBooking admin code here...)

@admin.register(BlockedTime)
class BlockedTimeAdmin(admin.ModelAdmin):
    list_display = ('date', 'timeslot', 'reason')
    list_filter = ('date',)
    search_fields = ('reason', 'timeslot')

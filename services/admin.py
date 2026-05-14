# services/admin.py
from django.contrib import admin
from .models import Service, ServiceProvider, ServiceBooking, ServiceCategory

# ==========================================
# NEW: Service Category Admin
# ==========================================
@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'display_order', 'is_active')
    list_filter = ('tenant', 'is_active')
    search_fields = ('name',)
    ordering = ('tenant', 'display_order', 'name')


# ==========================================
# UPDATED: Service Admin
# ==========================================
@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    # Added category, tenant, display_order, and is_addon_only to the table view
    list_display = ('name', 'category', 'tenant', 'price_fixed', 'price_per_hour', 'display_order', 'is_addon_only', 'is_active')
    # Added category, tenant, and is_addon_only to the side filters
    list_filter = ('tenant', 'is_active', 'is_addon_only', 'category', 'requires_assigned_staff')
    search_fields = ('name', 'category__name')
    ordering = ('tenant', 'category__display_order', 'display_order', 'name')


# ==========================================
# Service Provider Admin (unchanged)
# ==========================================
@admin.register(ServiceProvider)
class ServiceProviderAdmin(admin.ModelAdmin):
    list_display = ('user', 'service', 'tenant', 'is_active') # Added tenant for visibility
    list_filter = ('tenant', 'is_active')
    search_fields = ('user__email', 'service__name')


# ==========================================
# Service Booking Admin (unchanged)
# ==========================================
@admin.register(ServiceBooking)
class ServiceBookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'service', 'tenant', 'customer_email', 'start_time', 'status', 'total_price') # Added tenant for visibility
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

# services/admin.py
from django.contrib import admin
from .models import Service, ServiceProvider, ServiceBooking


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_fixed', 'price_per_hour', 'duration_minutes')
    list_filter = ('is_active', 'requires_assigned_staff')
    search_fields = ('name',)


@admin.register(ServiceProvider)
class ServiceProviderAdmin(admin.ModelAdmin):
    list_display = ('user', 'service', 'is_active')
    list_filter = ('is_active', 'tenant')
    search_fields = ('user__email', 'service__name')


@admin.register(ServiceBooking)
class ServiceBookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'service', 'customer_email', 'start_time', 'status', 'total_price')
    list_filter = ('status', 'start_time', 'tenant')
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

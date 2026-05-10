# services/admin.py
from django.contrib import admin
from .models import Service, ServiceProvider, ServiceBooking


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_fixed', 'price_per_hour', 'duration_minutes')
    list_filter = ('is_active', 'requires_assigned_staff')


@admin.register(ServiceProvider)
class ServiceProviderAdmin(admin.ModelAdmin):
    list_display = ('user', 'service', 'is_active')
    list_filter = ('is_active', 'tenant')


@admin.register(ServiceBooking)
class ServiceBookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'service', 'customer', 'start_time', 'status', 'total_price')
    list_filter = ('status', 'start_time', 'tenant')
    search_fields = ('customer__email', 'service__name')

# payments/admin.py
from django.contrib import admin
from .models import Booking, BookingItem


class BookingItemInline(admin.TabularInline):
    """Show booking items inline on the booking admin page"""
    model = BookingItem
    extra = 0
    readonly_fields = ('product_name', 'product_sku', 'variant_name', 
                       'unit_price', 'quantity', 'line_total', 'product_image')
    can_delete = False
    fields = ('product_name', 'product_sku', 'quantity', 'unit_price', 'line_total')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_email', 'customer_name', 'status', 
                    'total', 'created_at', 'paid_at')
    list_filter = ('status', 'is_gift', 'created_at', 'tenant')
    search_fields = ('customer_email', 'customer_name', 'id', 'stripe_checkout_session_id')
    readonly_fields = ('id', 'created_at', 'updated_at', 'paid_at', 
                       'stripe_checkout_session_id', 'stripe_payment_intent_id')
    fieldsets = (
        ('Customer Information', {
            'fields': ('tenant', 'customer_email', 'customer_name', 'ip_address')
        }),
        ('Booking Status', {
            'fields': ('status', 'created_at', 'paid_at', 'updated_at')
        }),
        ('Pricing', {
            'fields': ('subtotal', 'shipping_cost', 'total')
        }),
        ('Gift Options', {
            'fields': ('is_gift', 'gift_message')
        }),
        ('Stripe Integration', {
            'fields': ('stripe_checkout_session_id', 'stripe_payment_intent_id')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
    )
    inlines = [BookingItemInline]
    ordering = ('-created_at',)


@admin.register(BookingItem)
class BookingItemAdmin(admin.ModelAdmin):
    list_display = ('booking', 'product_name', 'quantity', 'unit_price', 'line_total')
    list_filter = ('booking__status', 'tenant')
    search_fields = ('booking__id', 'product_name', 'product_sku')
    readonly_fields = ('booking', 'product', 'product_name', 'product_sku', 
                       'variant_name', 'unit_price', 'quantity', 'line_total', 'product_image')

from django.contrib import admin
from .models import Booking, BookingItem

class BookingItemInline(admin.TabularInline):
    """Shows the products purchased inside the Booking page"""
    model = BookingItem
    extra = 0
    can_delete = False
    fields = ('product_name', 'variant_name', 'quantity', 'unit_price', 'line_total')
    readonly_fields = ('product_name', 'variant_name', 'quantity', 'unit_price', 'line_total')

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    # 1. Columns shown in the main list
    list_display = (
        'id', 
        'customer_email', 
        'customer_name',
        'status', 
        'total', 
        'created_at',
        'is_gift'
    )
    
    # 2. Sidebar Filters
    list_filter = ('status', 'created_at', 'is_gift')
    
    # 3. Search Bar (searches emails, names, and Stripe IDs)
    search_fields = (
        'customer_email', 
        'customer_name', 
        'id', 
        'stripe_checkout_session_id',
        'stripe_payment_intent_id'
    )

    # 4. Read-only fields (prevent accidental tampering with financial data)
    readonly_fields = (
        'created_at', 
        'updated_at', 
        'paid_at', 
        'stripe_checkout_session_id', 
        'stripe_payment_intent_id',
        'ip_address',
        'subtotal',     # Backend calculated
        'total',        # Backend calculated
        'shipping_cost' # Backend calculated
    )

    # 5. Layout of the Detail Page
    fieldsets = (
        ('Customer Details', {
            'fields': ('customer_email', 'customer_name', 'ip_address')
        }),
        ('Order Status', {
            'fields': ('status', 'created_at', 'paid_at')
        }),
        ('Financials', {
            'fields': ('subtotal', 'shipping_cost', 'total')
        }),
        ('Gift Options', {
            'fields': ('is_gift', 'gift_message')
        }),
        ('Stripe Data', {
            'classes': ('collapse',), # Collapsible section
            'fields': ('stripe_checkout_session_id', 'stripe_payment_intent_id', 'notes')
        }),
    )

    # 6. Include the items inline
    inlines = [BookingItemInline]

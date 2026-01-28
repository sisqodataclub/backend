"""
Core Admin - Tenant Management
"""
from django.contrib import admin
from .models import Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    """
    Admin interface for managing tenants/clients
    """
    list_display = [
        'name', 'domain', 'business_name', 
        'is_active', 'created_at'
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'domain', 'business_name', 'email']
    list_editable = ['is_active']
    
    fieldsets = (
        ('Tenant Identification', {
            'fields': ('name', 'domain')
        }),
        ('Business Information', {
            'fields': ('business_name', 'email', 'phone')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']

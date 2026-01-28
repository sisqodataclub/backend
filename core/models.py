"""
Core Models - Base classes for multi-tenant system
"""
from django.db import models


class Tenant(models.Model):
    """
    Tenant model - Represents each client/business
    """
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Internal name (e.g., 'client-a', 'acme-corp')"
    )
    domain = models.CharField(
        max_length=255,
        unique=True,
        help_text="Domain or subdomain (e.g., 'clienta.com' or 'clienta.yourdomain.com')"
    )
    
    # Business Information
    business_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Public-facing business name"
    )
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class TenantAwareModel(models.Model):
    """
    Abstract base model that adds tenant relationship to all models
    All your app models should inherit from this
    """
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='%(class)s_set',
        help_text="Which tenant/client owns this record"
    )
    
    class Meta:
        abstract = True

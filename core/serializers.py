from rest_framework import serializers

class TenantAwareSerializer(serializers.ModelSerializer):
    """Base serializer that automatically handles tenant field"""
    
    # Note: Serializers don't strictly use abstract=True like models, 
    # but this structure is fine for inheritance.
    
    def create(self, validated_data):
        """Create instance with tenant from request context"""
        request = self.context.get('request')
        
        # Security: Remove tenant if user tries to set it manually
        validated_data.pop('tenant', None)
        validated_data.pop('tenant_id', None)
        
        # 1. Try getting tenant from Request (Middleware)
        if request and hasattr(request, 'tenant'):
            validated_data['tenant'] = request.tenant
        else:
            # 2. Fallback: Try getting from Thread-Local (Background tasks/Shell)
            from .utils import get_current_tenant
            tenant = get_current_tenant()
            if tenant:
                validated_data['tenant'] = tenant
        
        # 3. Final Validation
        if 'tenant' not in validated_data:
            raise serializers.ValidationError({
                "tenant": "Tenant context is missing. Cannot create resource."
            })
        
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        """Update instance, ensuring tenant cannot be changed"""
        # Security: Prevent moving objects between tenants
        validated_data.pop('tenant', None)
        validated_data.pop('tenant_id', None)
        
        return super().update(instance, validated_data)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # User experience: Make tenant field read-only in API forms
        if 'tenant' in self.fields:
            self.fields['tenant'].read_only = True
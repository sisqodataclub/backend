# core/logging.py
import logging
from .utils import get_current_tenant

class TenantContextFilter(logging.Filter):
    """Add tenant context to log records"""
    
    def filter(self, record):
        tenant = get_current_tenant()
        if tenant:
            record.tenant = f"[{tenant.name}]"
        else:
            record.tenant = "[no-tenant]"
        return True


class RequestContextFilter(logging.Filter):
    """Add request context to log records"""
    
    def filter(self, record):
        from .utils import get_current_request
        
        request = get_current_request()
        if request:
            record.user = getattr(request.user, 'username', 'anonymous')
            record.path = request.path
            record.method = request.method
            record.ip = get_client_ip(request)
        else:
            record.user = 'system'
            record.path = 'N/A'
            record.method = 'N/A'
            record.ip = 'N/A'
        
        return True


def get_client_ip(request):
    """Extract client IP from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip or 'unknown'
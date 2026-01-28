# core/utils.py
import threading

# Thread-local storage for tenant context
# MUST be defined here and imported everywhere to avoid circular imports
_thread_locals = threading.local()

def get_current_tenant():
    """Get the current tenant from thread-local storage"""
    return getattr(_thread_locals, 'tenant', None)

def set_current_tenant(tenant):
    """Set the current tenant in thread-local storage"""
    _thread_locals.tenant = tenant

def get_current_request():
    """Get the current request from thread-local storage (optional)"""
    return getattr(_thread_locals, 'request', None)

def set_current_request(request):
    """Set the current request in thread-local storage (optional)"""
    _thread_locals.request = request

def clear_thread_locals():
    """Clear all thread-local data (for cleanup)"""
    if hasattr(_thread_locals, 'tenant'):
        del _thread_locals.tenant
    if hasattr(_thread_locals, 'request'):
        del _thread_locals.request
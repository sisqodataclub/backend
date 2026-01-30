"""
Main URL Configuration - Multi-Tenant E-Commerce SaaS
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core.views import HealthCheckView, RateLimitExceededView

urlpatterns = [
    # ============================================================================
    # 1. ADMIN INTERFACE (Tenant-aware via middleware)
    # ============================================================================
    path('admin/', admin.site.urls, name='admin'),
    
    # ============================================================================
    # 2. API ENDPOINTS (Tenant-aware via middleware)
    # ============================================================================
    # ============================================================================
    # 2. API ENDPOINTS (Tenant-aware via middleware)
    # ============================================================================
    path('api/', include('products.urls')),
    path('api/payments/', include('payments.urls')),
    
    # ============================================================================
    # 3. HEALTH & MONITORING (No tenant required)
    # ============================================================================
    path('health/', HealthCheckView.as_view(), name='health_check'),
    path('health/ready/', HealthCheckView.as_view(), name='health_ready'),
    path('health/live/', HealthCheckView.as_view(), name='health_live'),
    
    # ============================================================================
    # 4. ERROR HANDLERS
    # ============================================================================
    path('rate-limit-exceeded/', RateLimitExceededView.as_view(), name='rate_limit_exceeded'),
]

# ============================================================================
# ERROR HANDLING (Django will use these automatically)
# ============================================================================
handler400 = 'core.views.bad_request_view'
handler403 = 'core.views.permission_denied_view'
handler404 = 'core.views.page_not_found_view'
handler429 = RateLimitExceededView.as_view()  # django-ratelimit
handler500 = 'core.views.server_error_view'

# ============================================================================
# DEVELOPMENT ONLY
# ============================================================================
if settings.DEBUG:
    # Serve static/media files
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    
    # Debug toolbar
    try:
        import debug_toolbar
        urlpatterns += [
            path('__debug__/', include(debug_toolbar.urls)),
        ]
    except ImportError:
        pass
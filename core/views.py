"""
Core Views - Health Checks and Error Handling
"""

from .umami_service import UmamiService
from django.http import JsonResponse
from django.views import View
from django.utils import timezone
from django.db import connection
from django.core.cache import cache
from django.conf import settings

import requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response





class HealthCheckView(View):
    """
    Comprehensive health check endpoint
    """
    
    def get(self, request):
        """Check system health"""
        checks = {}
        
        # Database check
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            checks['database'] = {'status': 'healthy'}
        except Exception as e:
            checks['database'] = {'status': 'unhealthy', 'error': str(e)}
        
        # Cache check
        try:
            cache.set('health_check', 'ok', 1)
            if cache.get('health_check') == 'ok':
                checks['cache'] = {'status': 'healthy'}
            else:
                checks['cache'] = {'status': 'unhealthy', 'error': 'Cache not working'}
        except Exception as e:
            checks['cache'] = {'status': 'unhealthy', 'error': str(e)}
        
        # Overall status
        all_healthy = all(check['status'] == 'healthy' for check in checks.values())
        
        response = {
            'status': 'healthy' if all_healthy else 'unhealthy',
            'timestamp': timezone.now().isoformat(),
            'checks': checks
        }
        
        status_code = 200 if all_healthy else 503
        return JsonResponse(response, status=status_code)


class RateLimitExceededView(View):
    """
    Custom view for rate limit exceeded errors
    """
    
    def dispatch(self, request, *args, **kwargs):
        return JsonResponse(
            {
                "detail": "Rate limit exceeded. Please try again later.",
                "code": "rate_limit_exceeded"
            },
            status=429
        )


# ============================================================================
# ERROR HANDLERS (Called automatically by Django)
# ============================================================================

def bad_request_view(request, exception=None):
    """400 Bad Request"""
    return JsonResponse(
        {
            "detail": "Bad request.",
            "code": "bad_request"
        },
        status=400
    )


def permission_denied_view(request, exception=None):
    """403 Forbidden"""
    return JsonResponse(
        {
            "detail": "Permission denied.",
            "code": "permission_denied"
        },
        status=403
    )


def page_not_found_view(request, exception=None):
    """404 Not Found"""
    return JsonResponse(
        {
            "detail": "Resource not found.",
            "code": "not_found",
            "path": request.path
        },
        status=404
    )


def server_error_view(request, exception=None):
    """500 Internal Server Error"""
    # Log the error (in production, this would go to Sentry/Logging)
    if settings.DEBUG and exception:
        error_detail = str(exception)
    else:
        error_detail = "Internal server error"
    
    return JsonResponse(
        {
            "detail": error_detail,
            "code": "server_error"
        },
        status=500
    )


# Add this to the "ERROR HANDLERS" section in core/views.py

def csrf_failure(request, reason=""):
    """Custom JSON response for CSRF failures"""
    return JsonResponse(
        {
            "detail": "CSRF verification failed. Request aborted.",
            "code": "csrf_failure",
            "reason": reason,
            "help": "Ensure 'X-CSRFToken' header is sent with the cookie value."
        },
        status=403
    )










# ============================================================================
# SUPERSET PROXY VIEWS (Dashboard API)
# ============================================================================

# ============================================================================
# SUPERSET PROXY VIEWS (Dashboard API)
# ============================================================================
import requests
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def superset_dashboard_data(request):
    """Securely fetches combined data from Superset and Umami for the dashboard."""

    if not hasattr(request, 'tenant') or not request.tenant:
        return Response({"error": "No active tenant associated with this token."}, status=403)

    tenant_name = request.tenant.name
    kpis = []

    # --- 1. Fetch Superset Data ---
    login_payload = {
        "username": settings.SUPERSET_ADMIN_USERNAME,
        "password": settings.SUPERSET_ADMIN_PASSWORD,
        "provider": "db"
    }

    try:
        auth_response = requests.post(f"{settings.SUPERSET_URL}/api/v1/security/login", json=login_payload)
        auth_response.raise_for_status()
        access_token = auth_response.json().get("access_token")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        data_response = requests.get(
            f"{settings.SUPERSET_URL}/api/v1/chart/1/data/",
            headers=headers
        )
        data_response.raise_for_status()

        raw_data = data_response.json().get('result', [{}])[0].get('data', [])
        count = raw_data[0].get('count', 0) if raw_data else 0

        kpis.append({ "id": '1', "title": 'Total Bookings', "value": count, "change": 0, "prefix": "" })

    except requests.exceptions.RequestException as e:
        logger.error(f"Superset error: {str(e)}")
        kpis.append({ "id": '1', "title": 'Total Bookings', "value": "Error", "change": 0, "prefix": "" })
    except Exception as e:
        logger.error(f"Superset error: {str(e)}")
        kpis.append({ "id": '1', "title": 'Total Bookings', "value": "Error", "change": 0, "prefix": "" })


    # --- 2. Fetch Umami Data ---
    umami_svc = UmamiService()
    umami_stats = umami_svc.get_last_24h_stats()

    if umami_stats:
        pageviews = umami_stats.get("pageviews", {}).get("value", 0)
        visitors = umami_stats.get("visitors", {}).get("value", 0)
        
        kpis.append({ "id": 'umami_1', "title": 'Page Views (24h)', "value": pageviews, "change": 0 })
        kpis.append({ "id": 'umami_2', "title": 'Unique Visitors', "value": visitors, "change": 0 })
    else:
        kpis.append({ "id": 'umami_1', "title": 'Page Views (24h)', "value": "N/A", "change": 0 })
        kpis.append({ "id": 'umami_2', "title": 'Unique Visitors', "value": "N/A", "change": 0 })

    # --- 3. Return Combined Data ---
    return Response({
        "kpis": kpis
    })

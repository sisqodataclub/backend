"""
Core Views - Health Checks and Error Handling
"""
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
    """Securely fetches data from Superset for the logged-in user's tenant"""

    if not hasattr(request, 'tenant') or not request.tenant:
        return Response({"error": "No active tenant associated with this token."}, status=403)

    # In an enterprise environment, tenant data separation should be 
    # handled by Superset's Row Level Security (RLS), not API filters.
    tenant_name = request.tenant.name

    login_payload = {
        "username": settings.SUPERSET_ADMIN_USERNAME,
        "password": settings.SUPERSET_ADMIN_PASSWORD,
        "provider": "db"
    }

    try:
        # 1. Authenticate with Superset to get the access token
        auth_response = requests.post(f"{settings.SUPERSET_URL}/api/v1/security/login", json=login_payload)
        auth_response.raise_for_status()
        access_token = auth_response.json().get("access_token")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # 2. Fetch the data using a GET request (No JSON payload allowed here)
        data_response = requests.get(
            f"{settings.SUPERSET_URL}/api/v1/chart/1/data/",
            headers=headers
        )
        data_response.raise_for_status()

        # 3. Safely parse the returning data
        raw_data = data_response.json().get('result', [{}])[0].get('data', [])
        
        # Depending on how your Superset chart is configured, the key might be 'count' or 'SUM(bookings)'
        count = raw_data[0].get('count', 0) if raw_data else 0

        # 4. Return the formatted KPI to your React frontend
        return Response({
            "kpis": [
                { "id": '1', "title": 'Total Bookings', "value": count, "change": 0, "prefix": "" }
            ]
        })

    except requests.exceptions.RequestException as e:
        return Response({"error": "Failed to communicate with BI engine", "details": str(e)}, status=502)
    except Exception as e:
        return Response({"error": "Internal server error", "details": str(e)}, status=500)

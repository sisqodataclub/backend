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
import logging
from datetime import datetime
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .umami_service import UmamiService

logger = logging.getLogger(__name__)

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


    # --- 2. Initialize Umami Service ---
    umami_svc = UmamiService()


    # --- 3. Fetch Umami 24h KPIs ---
    umami_stats = umami_svc.get_last_24h_stats()

    if umami_stats:
        pv_raw = umami_stats.get("pageviews", 0)
        pageviews = pv_raw.get("value", 0) if isinstance(pv_raw, dict) else pv_raw

        vis_raw = umami_stats.get("visitors", 0)
        visitors = vis_raw.get("value", 0) if isinstance(vis_raw, dict) else vis_raw

        kpis.append({ "id": 'umami_1', "title": 'Page Views (24h)', "value": pageviews, "change": 0 })
        kpis.append({ "id": 'umami_2', "title": 'Unique Visitors', "value": visitors, "change": 0 })
    else:
        kpis.append({ "id": 'umami_1', "title": 'Page Views (24h)', "value": "N/A", "change": 0 })
        kpis.append({ "id": 'umami_2', "title": 'Unique Visitors', "value": "N/A", "change": 0 })


    # --- 4. Fetch Dynamic Timeline based on React's request ---
    # Default to 7 Days if React doesn't ask for a specific preset
    preset = request.GET.get('preset', '7D')
    
    if preset == '24h':
        chart_days = 1
        chart_unit = 'hour'
    elif preset == '30D':
        chart_days = 30
        chart_unit = 'day'
    elif preset == 'This Year':
        chart_days = 365
        chart_unit = 'month'
    else: # Default 7D
        chart_days = 7
        chart_unit = 'day'

    timeline_raw = umami_svc.get_traffic_timeline(days=chart_days, unit=chart_unit)
    chart_data = []

    if timeline_raw:
        # Group the data based on the requested unit
        pv_dict = {item['x'][:10] if chart_unit != 'hour' else item['x']: item['y'] for item in timeline_raw.get('pageviews', [])}
        vis_dict = {item['x'][:10] if chart_unit != 'hour' else item['x']: item['y'] for item in timeline_raw.get('sessions', [])}
        
        all_dates = sorted(list(set(list(pv_dict.keys()) + list(vis_dict.keys()))))
        
        for date_str in all_dates:
            try:
                # Format the date string perfectly for the frontend chart
                if chart_unit == 'hour':
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00')) if 'T' in date_str else datetime.strptime(date_str[:13], '%Y-%m-%d %H')
                    formatted_date = dt.strftime('%H:00')
                elif chart_unit == 'month':
                    dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
                    formatted_date = dt.strftime('%b %Y') # e.g. "Oct 2023"
                else:
                    dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
                    formatted_date = dt.strftime('%a %d') if chart_days > 7 else dt.strftime('%a') # e.g. "Mon 24" or just "Mon"
                    
                chart_data.append({
                    "date": formatted_date,
                    "views": pv_dict.get(date_str, 0),
                    "visitors": vis_dict.get(date_str, 0)
                })
            except Exception:
                continue


    # --- 5. Fetch Device Metrics for Donut Chart ---
    # We keep this at 7 days by default, or you can also pass `days=chart_days` here if you want it to match!
    device_raw = umami_svc.get_metrics(metric_type="device", days=7)
    device_data = []

    if device_raw:
        for item in device_raw:
            device_data.append({
                "name": str(item.get("x", "Unknown")).capitalize(),
                "value": item.get("y", 0)
            })


    # --- 6. Return Combined Payload ---
    return Response({
        "kpis": kpis,
        "traffic_chart": chart_data,   # Now sending just ONE dynamically formatted chart
        "device_chart": device_data
    })

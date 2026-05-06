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
# ============================================================================
# ============================================================================
# SUPERSET PROXY VIEWS (Dashboard API)
# ============================================================================
import requests
import logging
from datetime import datetime, timedelta
from collections import defaultdict
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

    # --- Determine Global Time Filters from React ---
    preset = request.GET.get('preset', '7D')
    chart_unit = request.GET.get('unit', 'day')
    is_comparing = request.GET.get('compare') == 'true'
    compare_type = request.GET.get('compareType', 'prev_period')

    # Catch custom dates from React
    custom_start_date = request.GET.get('startDate')
    custom_end_date = request.GET.get('endDate')

    custom_start_at = None
    custom_end_at = None
    chart_days = 7 # Default fallback

    # Parse Custom Dates
    if preset == 'Custom' and custom_start_date and custom_end_date:
        try:
            dt_start = datetime.strptime(custom_start_date, '%Y-%m-%d')
            dt_end = datetime.strptime(custom_end_date, '%Y-%m-%d')
            # Make the end date inclusive by shifting it to the end of the day
            dt_end = dt_end.replace(hour=23, minute=59, second=59)

            custom_start_at = int(dt_start.timestamp() * 1000)
            custom_end_at = int(dt_end.timestamp() * 1000)
            
            diff = dt_end - dt_start
            chart_days = max(1, diff.days)
        except Exception:
            preset = '7D' # Safety fallback if date string format is corrupted

    # Standard Presets
    if preset == '24h':
        chart_days = 1
        chart_unit = 'hour'
    elif preset == '30D':
        chart_days = 30
    elif preset == 'This Year':
        chart_days = 365
    elif preset == '7D':
        chart_days = 7

    kpis = []

    # --- 1. Fetch Superset Data (Total Bookings) ---
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

    except Exception as e:
        logger.error(f"Superset error: {str(e)}")
        kpis.append({ "id": '1', "title": 'Total Bookings', "value": "Error", "change": 0, "prefix": "" })


    # --- 2. Initialize Umami Service ---
    umami_svc = UmamiService()


    # --- 3. Fetch Umami KPIs ---
    umami_stats = umami_svc.get_stats(days=chart_days, custom_start_at=custom_start_at, custom_end_at=custom_end_at)
    
    # Format the KPI label nicely for custom dates
    if preset == 'Custom' and custom_start_date and custom_end_date:
        time_label = f"({datetime.strptime(custom_start_date, '%Y-%m-%d').strftime('%b %d')} - {datetime.strptime(custom_end_date, '%Y-%m-%d').strftime('%b %d')})"
    else:
        time_label = f"({preset})"

    if umami_stats:
        pv_raw = umami_stats.get("pageviews", 0)
        pageviews = pv_raw.get("value", 0) if isinstance(pv_raw, dict) else pv_raw

        vis_raw = umami_stats.get("visitors", 0)
        visitors = vis_raw.get("value", 0) if isinstance(vis_raw, dict) else vis_raw

        kpis.append({ "id": 'umami_1', "title": f'Page Views {time_label}', "value": pageviews, "change": 0 })
        kpis.append({ "id": 'umami_2', "title": f'Unique Visitors {time_label}', "value": visitors, "change": 0 })
    else:
        kpis.append({ "id": 'umami_1', "title": f'Page Views {time_label}', "value": "N/A", "change": 0 })
        kpis.append({ "id": 'umami_2', "title": f'Unique Visitors {time_label}', "value": "N/A", "change": 0 })


    # --- 4. Fetch Dynamic Timeline (With Manual Weekly Aggregation) ---
    # Umami does not natively support 'week'. We must fetch 'day' and group it ourselves.
    umami_query_unit = 'day' if chart_unit == 'week' else chart_unit

    # Fetch Current Period
    timeline_raw = umami_svc.get_traffic_timeline(
        days=chart_days, unit=umami_query_unit, offset_days=0,
        custom_start_at=custom_start_at, custom_end_at=custom_end_at
    )

    # Fetch Previous Period
    prev_timeline_raw = None
    if is_comparing:
        offset = chart_days if compare_type == 'prev_period' else 365
        prev_timeline_raw = umami_svc.get_traffic_timeline(
            days=chart_days, unit=umami_query_unit, offset_days=offset,
            custom_start_at=custom_start_at, custom_end_at=custom_end_at
        )

    chart_data = []

    # Helper function to group data and handle weekly math
    def aggregate_data(raw_data, is_weekly):
        pvs = defaultdict(int)
        viss = defaultdict(int)
        if not raw_data: return pvs, viss

        for item in raw_data.get('pageviews', []):
            key = item['x']
            if is_weekly and len(key) >= 10:
                dt = datetime.strptime(key[:10], '%Y-%m-%d')
                monday = dt - timedelta(days=dt.weekday()) # Roll back to the nearest Monday
                key = monday.strftime('%Y-%m-%d')
            pvs[key] += item['y']

        for item in raw_data.get('sessions', []):
            key = item['x']
            if is_weekly and len(key) >= 10:
                dt = datetime.strptime(key[:10], '%Y-%m-%d')
                monday = dt - timedelta(days=dt.weekday()) # Roll back to the nearest Monday
                key = monday.strftime('%Y-%m-%d')
            viss[key] += item['y']

        return dict(pvs), dict(viss)

    if timeline_raw:
        is_weekly = (chart_unit == 'week')
        pv_dict, vis_dict = aggregate_data(timeline_raw, is_weekly)

        all_dates = sorted(list(set(list(pv_dict.keys()) + list(vis_dict.keys()))))

        # Process historical arrays
        prev_pvs = []
        prev_vis = []
        if prev_timeline_raw:
            prev_pv_dict, prev_vis_dict = aggregate_data(prev_timeline_raw, is_weekly)
            prev_pvs = [prev_pv_dict[k] for k in sorted(prev_pv_dict.keys())]
            prev_vis = [prev_vis_dict[k] for k in sorted(prev_vis_dict.keys())]

        # Zipper the arrays together
        for i, date_str in enumerate(all_dates):
            try:
                if 'T' in date_str:
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                elif chart_unit == 'hour':
                    dt = datetime.strptime(date_str[:13], '%Y-%m-%d %H')
                else:
                    dt = datetime.strptime(date_str[:10], '%Y-%m-%d')

                # Smart Label Formatting
                if chart_unit == 'hour':
                    if chart_days == 1:
                        formatted_date = dt.strftime('%H:00')
                    elif chart_days <= 7:
                        formatted_date = dt.strftime('%a %H:00')
                    else:
                        formatted_date = dt.strftime('%b %d, %H:00')
                elif chart_unit == 'month':
                    formatted_date = dt.strftime('%b %Y')
                elif chart_unit == 'week':
                    formatted_date = f"Week of {dt.strftime('%b %d')}"
                else:
                    formatted_date = dt.strftime('%b %d') if chart_days > 7 else dt.strftime('%a')

                data_point = {
                    "date": formatted_date,
                    "views": pv_dict.get(date_str, 0),
                    "visitors": vis_dict.get(date_str, 0)
                }

                if is_comparing:
                    data_point["prevViews"] = prev_pvs[i] if i < len(prev_pvs) else 0
                    data_point["prevVisitors"] = prev_vis[i] if i < len(prev_vis) else 0

                chart_data.append(data_point)
            except Exception:
                continue


    # --- 5. Fetch Device Metrics ---
    device_raw = umami_svc.get_metrics(metric_type="device", days=chart_days, custom_start_at=custom_start_at, custom_end_at=custom_end_at)
    device_data = []

    if device_raw:
        for item in device_raw:
            device_data.append({
                "name": str(item.get("x", "Unknown")).capitalize(),
                "value": item.get("y", 0)
            })


    return Response({
        "kpis": kpis,
        "traffic_chart": chart_data,
        "device_chart": device_data
    })

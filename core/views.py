# core/views.py
import requests
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.conf import settings
from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .umami_service import UmamiService

logger = logging.getLogger(__name__)

# ============================================================================
# Umami service instance (reused)
# ============================================================================
umami_svc = UmamiService()


# ----------------------------------------------------------------------
# Helper: get cached Superset access token
# ----------------------------------------------------------------------
def get_superset_access_token():
    """Obtain a Superset access token, using cache to avoid repeated logins."""
    token = cache.get('superset_access_token')
    if token:
        return token

    login_payload = {
        "username": settings.SUPERSET_ADMIN_USERNAME,
        "password": settings.SUPERSET_ADMIN_PASSWORD,
        "provider": "db"
    }
    try:
        response = requests.post(
            f"{settings.SUPERSET_URL}/api/v1/security/login",
            json=login_payload,
            timeout=10
        )
        response.raise_for_status()
        token = response.json().get("access_token")
        if token:
            # Cache token for 55 minutes (Superset tokens usually last 1 hour)
            cache.set('superset_access_token', token, 3300)
            return token
    except Exception as e:
        logger.error(f"Failed to obtain Superset token: {str(e)}")
    return None


# ----------------------------------------------------------------------
# Helper: fetch data for a single chart
# ----------------------------------------------------------------------
def fetch_superset_chart(chart_id, access_token):
    """Fetch data for one chart. Returns (chart_id, data_dict) or (chart_id, None) on error."""
    if not access_token:
        return chart_id, None
    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        url = f"{settings.SUPERSET_URL}/api/v1/chart/{chart_id}/data/"
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
        # Extract the actual data rows (structure varies, but typical)
        raw_data = result.get('result', [{}])[0].get('data', [])
        return chart_id, raw_data
    except Exception as e:
        logger.error(f"Error fetching Superset chart {chart_id}: {str(e)}")
        return chart_id, None


# ----------------------------------------------------------------------
# Main view
# ----------------------------------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def superset_dashboard_data(request):
    """
    Securely fetches combined data from Superset (multiple charts) and Umami.

    Query parameters:
    - chart_ids: comma-separated list of Superset chart IDs (optional, default: 1)
    - preset, unit, compare, compareType, startDate, endDate: as before (for Umami)
    """
    # ---- Tenant check ----
    if not hasattr(request, 'tenant') or not request.tenant:
        return Response({"error": "No active tenant associated with this token."}, status=403)

    # ---- Parse chart_ids ----
    chart_ids_param = request.GET.get('chart_ids', '')
    chart_ids = []
    if chart_ids_param:
        chart_ids = [int(cid.strip()) for cid in chart_ids_param.split(',') if cid.strip().isdigit()]
    # Backward compatibility: if no chart_ids given, use chart 1 (total bookings)
    if not chart_ids:
        chart_ids = [1]

    # ---- Time filter logic (unchanged from original) ----
    preset = request.GET.get('preset', '7D')
    chart_unit = request.GET.get('unit', 'day')
    is_comparing = request.GET.get('compare') == 'true'
    compare_type = request.GET.get('compareType', 'prev_period')
    custom_start_date = request.GET.get('startDate')
    custom_end_date = request.GET.get('endDate')
    custom_start_at = None
    custom_end_at = None
    chart_days = 7

    if preset == 'Custom' and custom_start_date and custom_end_date:
        try:
            dt_start = datetime.strptime(custom_start_date, '%Y-%m-%d')
            dt_end = datetime.strptime(custom_end_date, '%Y-%m-%d')
            dt_end = dt_end.replace(hour=23, minute=59, second=59)
            custom_start_at = int(dt_start.timestamp() * 1000)
            custom_end_at = int(dt_end.timestamp() * 1000)
            chart_days = max(1, (dt_end - dt_start).days)
        except Exception:
            preset = '7D'

    if preset == '24h':
        chart_days = 1
        chart_unit = 'hour'
    elif preset == '30D':
        chart_days = 30
    elif preset == 'This Year':
        chart_days = 365
    elif preset == '7D':
        chart_days = 7

    # ---- 1. Fetch Superset charts ----
    access_token = get_superset_access_token()
    superset_charts = {}
    errors = {}

    if access_token:
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_chart = {
                executor.submit(fetch_superset_chart, cid, access_token): cid
                for cid in chart_ids
            }
            for future in as_completed(future_to_chart):
                cid = future_to_chart[future]
                try:
                    chart_id, data = future.result()
                    if data is not None:
                        superset_charts[chart_id] = data
                    else:
                        errors[chart_id] = "Failed to fetch chart data"
                except Exception as e:
                    logger.error(f"Unexpected error fetching chart {cid}: {str(e)}")
                    errors[cid] = str(e)
    else:
        for cid in chart_ids:
            errors[cid] = "Could not obtain Superset access token"

    # ---- 2. Umami KPIs ----
    kpis = []
    umami_stats = umami_svc.get_stats(days=chart_days, custom_start_at=custom_start_at, custom_end_at=custom_end_at)
    if preset == 'Custom' and custom_start_date and custom_end_date:
        time_label = f"({datetime.strptime(custom_start_date, '%Y-%m-%d').strftime('%b %d')} - {datetime.strptime(custom_end_date, '%Y-%m-%d').strftime('%b %d')})"
    else:
        time_label = f"({preset})"

    if umami_stats:
        pv_raw = umami_stats.get("pageviews", 0)
        pageviews = pv_raw.get("value", 0) if isinstance(pv_raw, dict) else pv_raw
        vis_raw = umami_stats.get("visitors", 0)
        visitors = vis_raw.get("value", 0) if isinstance(vis_raw, dict) else vis_raw
        kpis.append({"id": "umami_1", "title": f"Page Views {time_label}", "value": pageviews, "change": 0})
        kpis.append({"id": "umami_2", "title": f"Unique Visitors {time_label}", "value": visitors, "change": 0})
    else:
        kpis.append({"id": "umami_1", "title": f"Page Views {time_label}", "value": "N/A", "change": 0})
        kpis.append({"id": "umami_2", "title": f"Unique Visitors {time_label}", "value": "N/A", "change": 0})

    # ---- 3. Umami timeline ----
    umami_query_unit = 'day' if chart_unit == 'week' else chart_unit
    timeline_raw = umami_svc.get_traffic_timeline(
        days=chart_days, unit=umami_query_unit, offset_days=0,
        custom_start_at=custom_start_at, custom_end_at=custom_end_at
    )
    prev_timeline_raw = None
    if is_comparing:
        offset = chart_days if compare_type == 'prev_period' else 365
        prev_timeline_raw = umami_svc.get_traffic_timeline(
            days=chart_days, unit=umami_query_unit, offset_days=offset,
            custom_start_at=custom_start_at, custom_end_at=custom_end_at
        )

    chart_data = []

    def aggregate_data(raw_data, is_weekly):
        pvs = defaultdict(int)
        viss = defaultdict(int)
        if not raw_data:
            return pvs, viss
        for item in raw_data.get('pageviews', []):
            key = item['x']
            if is_weekly and len(key) >= 10:
                dt = datetime.strptime(key[:10], '%Y-%m-%d')
                monday = dt - timedelta(days=dt.weekday())
                key = monday.strftime('%Y-%m-%d')
            pvs[key] += item['y']
        for item in raw_data.get('sessions', []):
            key = item['x']
            if is_weekly and len(key) >= 10:
                dt = datetime.strptime(key[:10], '%Y-%m-%d')
                monday = dt - timedelta(days=dt.weekday())
                key = monday.strftime('%Y-%m-%d')
            viss[key] += item['y']
        return dict(pvs), dict(viss)

    if timeline_raw:
        is_weekly = (chart_unit == 'week')
        pv_dict, vis_dict = aggregate_data(timeline_raw, is_weekly)
        all_dates = sorted(set(pv_dict.keys()) | set(vis_dict.keys()))
        prev_pvs = []
        prev_vis = []
        if prev_timeline_raw:
            prev_pv_dict, prev_vis_dict = aggregate_data(prev_timeline_raw, is_weekly)
            prev_pvs = [prev_pv_dict[k] for k in sorted(prev_pv_dict.keys())]
            prev_vis = [prev_vis_dict[k] for k in sorted(prev_vis_dict.keys())]

        for i, date_str in enumerate(all_dates):
            try:
                if 'T' in date_str:
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                elif chart_unit == 'hour':
                    dt = datetime.strptime(date_str[:13], '%Y-%m-%d %H')
                else:
                    dt = datetime.strptime(date_str[:10], '%Y-%m-%d')

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

    # ---- 4. Umami device metrics ----
    device_raw = umami_svc.get_metrics(metric_type="device", days=chart_days, custom_start_at=custom_start_at, custom_end_at=custom_end_at)
    device_data = []
    if device_raw:
        for item in device_raw:
            device_data.append({
                "name": str(item.get("x", "Unknown")).capitalize(),
                "value": item.get("y", 0)
            })

    # ---- 5. Umami top pages (NEW) ----
    top_pages = []
    try:
        pages_raw = umami_svc.get_pages(limit=5, days=chart_days, custom_start_at=custom_start_at, custom_end_at=custom_end_at)
        if pages_raw:
            for item in pages_raw:
                top_pages.append({
                    "url": item.get("url", ""),
                    "visits": item.get("visits", 0)
                })
    except Exception as e:
        logger.error(f"Failed to fetch Umami top pages: {str(e)}")

    # ---- 6. Build final response ----
    response = {
        "kpis": kpis,
        "traffic_chart": chart_data,
        "device_chart": device_data,
        "top_pages": top_pages,                      # <-- NEW
        "superset_charts": superset_charts,
        "superset_errors": errors
    }

    return Response(response)

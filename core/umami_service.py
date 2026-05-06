import requests
import time
import logging
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

class UmamiService:
    def __init__(self):
        self.api_url = getattr(settings, 'UMAMI_API_URL', "https://analytics.ddeepcleaningservices.com")
        self.website_id = getattr(settings, 'UMAMI_WEBSITE_ID', None)
        self.username = getattr(settings, 'UMAMI_USERNAME', None)
        self.password = getattr(settings, 'UMAMI_PASSWORD', None)

    def is_configured(self):
        return all([self.api_url, self.website_id, self.username, self.password])

    def _get_auth_token(self):
        cache_key = "umami_auth_token"
        token = cache.get(cache_key)
        if token: return token
        try:
            response = requests.post(f"{self.api_url}/api/auth/login", json={
                "username": self.username,
                "password": self.password
            }, timeout=15) # Bumped login timeout slightly
            response.raise_for_status()
            token = response.json().get("token")
            if token: cache.set(cache_key, token, 12 * 60 * 60)
            return token
        except Exception as e:
            logger.error(f"Failed to authenticate with Umami: {str(e)}")
            return None

    def get_stats(self, days=1, custom_start_at=None, custom_end_at=None):
        if not self.is_configured(): return None
        token = self._get_auth_token()
        if not token: return None
        try:
            end_at = custom_end_at if custom_end_at else int(time.time() * 1000)
            start_at = custom_start_at if custom_start_at else end_at - (days * 24 * 60 * 60 * 1000)
            headers = { "Authorization": f"Bearer {token}", "Content-Type": "application/json" }
            url = f"{self.api_url}/api/websites/{self.website_id}/stats?startAt={start_at}&endAt={end_at}"
            
            # Increased timeout to 30s to allow heavy "This Year" queries
            response = requests.get(url, headers=headers, timeout=30) 
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch Umami stats: {str(e)}")
            return None

    def get_traffic_timeline(self, days=7, unit="day", offset_days=0, custom_start_at=None, custom_end_at=None):
        if not self.is_configured(): return None
        token = self._get_auth_token()
        if not token: return None
        try:
            base_end = custom_end_at if custom_end_at else int(time.time() * 1000)
            base_start = custom_start_at if custom_start_at else base_end - (days * 24 * 60 * 60 * 1000)
            end_at = base_end - (offset_days * 24 * 60 * 60 * 1000)
            start_at = base_start - (offset_days * 24 * 60 * 60 * 1000)
            headers = { "Authorization": f"Bearer {token}", "Content-Type": "application/json" }
            url = f"{self.api_url}/api/websites/{self.website_id}/pageviews?startAt={start_at}&endAt={end_at}&unit={unit}&timezone=Europe/London"
            
            # Increased timeout to 30s so "This Year" daily queries don't fail!
            response = requests.get(url, headers=headers, timeout=30) 
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch Umami timeline: {str(e)}")
            return None

    def get_metrics(self, metric_type="device", days=7, custom_start_at=None, custom_end_at=None):
        if not self.is_configured(): return []
        token = self._get_auth_token()
        if not token: return []
        try:
            end_at = custom_end_at if custom_end_at else int(time.time() * 1000)
            start_at = custom_start_at if custom_start_at else end_at - (days * 24 * 60 * 60 * 1000)
            headers = { "Authorization": f"Bearer {token}", "Content-Type": "application/json" }
            url = f"{self.api_url}/api/websites/{self.website_id}/metrics?startAt={start_at}&endAt={end_at}&type={metric_type}"
            
            # Increased timeout to 30s
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch Umami {metric_type} metrics: {str(e)}")
            return []

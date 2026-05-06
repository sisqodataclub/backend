import requests
import time
import logging
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

class UmamiService:
    def __init__(self):
        # Defaulting to your dedicated analytics domain
        self.api_url = getattr(settings, 'UMAMI_API_URL', "https://analytics.ddeepcleaningservices.com")
        self.website_id = getattr(settings, 'UMAMI_WEBSITE_ID', None)
        self.username = getattr(settings, 'UMAMI_USERNAME', None)
        self.password = getattr(settings, 'UMAMI_PASSWORD', None)

    def is_configured(self):
        """Checks if all necessary environment variables are present."""
        return all([self.api_url, self.website_id, self.username, self.password])

    def _get_auth_token(self):
        """Fetches and caches the Umami auth token using Username/Password."""
        cache_key = "umami_auth_token"
        token = cache.get(cache_key)

        if token:
            return token

        try:
            response = requests.post(f"{self.api_url}/api/auth/login", json={
                "username": self.username,
                "password": self.password
            }, timeout=10)

            response.raise_for_status()
            token = response.json().get("token")

            if token:
                cache.set(cache_key, token, 12 * 60 * 60)

            return token

        except Exception as e:
            logger.error(f"Failed to authenticate with Umami: {str(e)}")
            return None

    def get_stats(self, days=1, custom_start_at=None, custom_end_at=None):
        """Fetches aggregate stats. Uses exact ms timestamps if provided, otherwise calculates from days."""
        if not self.is_configured():
            logger.warning("Umami service is missing credentials or website ID.")
            return None

        token = self._get_auth_token()
        if not token:
            return None

        try:
            # Prefer custom timestamps; otherwise fallback to rolling 'days' calculation
            end_at = custom_end_at if custom_end_at else int(time.time() * 1000)
            start_at = custom_start_at if custom_start_at else end_at - (days * 24 * 60 * 60 * 1000)

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            url = f"{self.api_url}/api/websites/{self.website_id}/stats?startAt={start_at}&endAt={end_at}"

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to fetch Umami stats: {str(e)}")
            return None

    def get_traffic_timeline(self, days=7, unit="day", offset_days=0, custom_start_at=None, custom_end_at=None):
        """Fetches pageviews/visitors timeline. Includes historical offset math for comparison."""
        if not self.is_configured():
            return None

        token = self._get_auth_token()
        if not token:
            return None

        try:
            # 1. Determine the base date range
            base_end = custom_end_at if custom_end_at else int(time.time() * 1000)
            base_start = custom_start_at if custom_start_at else base_end - (days * 24 * 60 * 60 * 1000)

            # 2. Shift the window backwards in time if an offset is requested (for comparison)
            end_at = base_end - (offset_days * 24 * 60 * 60 * 1000)
            start_at = base_start - (offset_days * 24 * 60 * 60 * 1000)

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            url = f"{self.api_url}/api/websites/{self.website_id}/pageviews?startAt={start_at}&endAt={end_at}&unit={unit}&timezone=Europe/London"

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to fetch Umami timeline: {str(e)}")
            return None

    def get_metrics(self, metric_type="device", days=7, custom_start_at=None, custom_end_at=None):
        """Fetches categorical metrics (device, os, etc.) inside the dynamic date range."""
        if not self.is_configured():
            return []

        token = self._get_auth_token()
        if not token:
            return []

        try:
            end_at = custom_end_at if custom_end_at else int(time.time() * 1000)
            start_at = custom_start_at if custom_start_at else end_at - (days * 24 * 60 * 60 * 1000)

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            url = f"{self.api_url}/api/websites/{self.website_id}/metrics?startAt={start_at}&endAt={end_at}&type={metric_type}"

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to fetch Umami {metric_type} metrics: {str(e)}")
            return []

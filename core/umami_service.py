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
            # Login to Umami using standard Username and Password
            response = requests.post(f"{self.api_url}/api/auth/login", json={
                "username": self.username,
                "password": self.password
            }, timeout=10)

            response.raise_for_status()
            token = response.json().get("token")

            if token:
                # Cache the token for 12 hours (Umami tokens usually last 24h)
                cache.set(cache_key, token, 12 * 60 * 60)

            return token

        except Exception as e:
            logger.error(f"Failed to authenticate with Umami: {str(e)}")
            return None

    def get_stats(self, days=1):
        """Fetches the aggregate stats (KPIs) for a dynamic number of days."""
        if not self.is_configured():
            logger.warning("Umami service is missing credentials or website ID.")
            return None

        token = self._get_auth_token()
        if not token:
            return None

        try:
            end_at = int(time.time() * 1000)
            start_at = end_at - (days * 24 * 60 * 60 * 1000)

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            url = f"{self.api_url}/api/websites/{self.website_id}/stats?startAt={start_at}&endAt={end_at}"

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to fetch Umami stats for {days} days: {str(e)}")
            return None

    def get_traffic_timeline(self, days=7, unit="day", offset_days=0):
        """Fetches pageviews/visitors. offset_days pushes the date window back in time."""
        if not self.is_configured():
            return None

        token = self._get_auth_token()
        if not token:
            return None

        try:
            # Step 1: Calculate the end point, shifted back by the offset
            end_at = int(time.time() * 1000) - (offset_days * 24 * 60 * 60 * 1000)
            # Step 2: Calculate the start point based on the requested days
            start_at = end_at - (days * 24 * 60 * 60 * 1000)

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            # Notice the {unit} variable dynamically placed in the URL
            url = f"{self.api_url}/api/websites/{self.website_id}/pageviews?startAt={start_at}&endAt={end_at}&unit={unit}&timezone=Europe/London"

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to fetch Umami timeline: {str(e)}")
            return None

    def get_metrics(self, metric_type="device", days=7):
        """Fetches categorical metrics (device, os, browser, country) for Donut charts."""
        if not self.is_configured():
            return []

        token = self._get_auth_token()
        if not token:
            return []

        try:
            end_at = int(time.time() * 1000)
            start_at = end_at - (days * 24 * 60 * 60 * 1000)

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            # Hit the /metrics endpoint for categorical breakdown
            url = f"{self.api_url}/api/websites/{self.website_id}/metrics?startAt={start_at}&endAt={end_at}&type={metric_type}"

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to fetch Umami {metric_type} metrics: {str(e)}")
            return []

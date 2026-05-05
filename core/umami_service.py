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
                cache.set(cache_key, token, 12 * 60 * 60) # Cache for 12 hours
                
            return token
            
        except Exception as e:
            logger.error(f"Failed to authenticate with Umami: {str(e)}")
            return None

    def get_last_24h_stats(self):
        """Fetches the aggregate stats for the last 24 hours."""
        if not self.is_configured():
            logger.warning("Umami service is missing credentials or website ID.")
            return None
            
        token = self._get_auth_token()
        if not token:
            return None
            
        try:
            end_at = int(time.time() * 1000)
            start_at = end_at - (24 * 60 * 60 * 1000)
            
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

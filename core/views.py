from django.shortcuts import render

# Create your views here.
from django.http import JsonResponse
from django.db import connection
from django.views import View
from django.utils import timezone  # ✅ Fixed import

class HealthCheckView(View):
    """Health check endpoint for Docker and load balancers"""
    
    def get(self, request):
        # Check database connection
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                db_ok = True
        except Exception:
            db_ok = False
        
        status = {
            'status': 'healthy' if db_ok else 'unhealthy',
            'database': 'connected' if db_ok else 'disconnected',
            'timestamp': timezone.now().isoformat(),
            'version': '1.0.0',  # You can make this dynamic
        }
        
        status_code = 200 if db_ok else 503
        return JsonResponse(status, status=status_code)
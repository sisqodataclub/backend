"""
Django settings for backend project - PRODUCTION READY
Multi-tenant SaaS configuration with security, caching, and logging
"""

import os
import sys
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ==============================================================================
# 1. ENVIRONMENT VALIDATION (Fail Fast - Production Critical)
# ==============================================================================
def get_env_var(var_name, default=None, required=False):
    """Safely get environment variable with validation"""
    value = os.environ.get(var_name, default)
    if required and not value:
        raise ValueError(f"❌ CRITICAL: Missing required environment variable: {var_name}")
    return value

# ==============================================================================
# 2. CORE SETTINGS
# ==============================================================================

SECRET_KEY = get_env_var('DJANGO_SECRET_KEY', 'django-insecure-dev-key-change-in-production')
DEBUG = get_env_var('DJANGO_DEBUG', 'False').lower() == 'true'

# Validate production environment variables
if not DEBUG:
    required_vars = ['DJANGO_SECRET_KEY', 'DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST']
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        sys.stderr.write(f"❌ CRITICAL ERROR: Missing environment variables in production: {', '.join(missing)}\n")
        sys.exit(1)

# Parse ALLOWED_HOSTS (handling empty strings to avoid errors)
raw_hosts = get_env_var('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,backend')
ALLOWED_HOSTS = [host.strip() for host in raw_hosts.split(',') if host.strip()]

# Always allow specific internal hosts for Docker health checks
for host in ['localhost', '127.0.0.1', 'backend']:
    if host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(host)

# Environment
DJANGO_ENV = get_env_var('DJANGO_ENV', 'development')

# ==============================================================================
# 3. APPLICATIONS & MIDDLEWARE
# ==============================================================================

INSTALLED_APPS = [
    # Third-Party Apps
    'rest_framework',
    'django_filters',
    'corsheaders',
    'django_ratelimit',  # Rate limiting support

    # Third-party apps required by django-sage-invoice
    'django.contrib.humanize',
    'django_jsonform',
    'import_export',
#    'sage_tools',
    'sage_invoice',     # The main invoice app
    'customer_notifications',


    
    # Local Apps
    'core',
    'products',
    'services',
    'payments',

    # Django Apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

# ============================================
# API & DRF CONFIGURATION (Requested)
# ============================================
REST_FRAMEWORK = {
    # Documentation
    'DEFAULT_SCHEMA_CLASS': 'rest_framework.schemas.openapi.AutoSchema',
    
    # Authentication
    'DEFAULT_AUTHENTICATION_CLASSES': [
	'core.authentication.ClerkAuthentication',
        'rest_framework.authentication.SessionAuthentication',  # For Admin Panel
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
}

# ==============================================================================
# 4. DATABASE
# ==============================================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': get_env_var('DB_NAME', 'backend_db'),
        'USER': get_env_var('DB_USER', 'postgres'),
        'PASSWORD': get_env_var('DB_PASSWORD', 'postgres'),
        'HOST': get_env_var('DB_HOST', 'db'),
        'PORT': get_env_var('DB_PORT', '5432'),
    }
}

# ==============================================================================
# 5. CORS SETTINGS
# ==============================================================================

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ['DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT']

# Explicitly allow X-Tenant header for multi-tenancy support
from corsheaders.defaults import default_headers
CORS_ALLOW_HEADERS = list(default_headers) + [
    'x-tenant',
    'x-agent-key',
]

if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
    # If in debug, keep origins empty as we allow all
    _temp_origins = CORS_ALLOWED_ORIGINS 
    CORS_ALLOWED_ORIGINS = [] 
else:
    CORS_ALLOW_ALL_ORIGINS = False
    
    # If no specific origins in .env, fallback to ALLOWED_HOSTS
    if not CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS = [f"http://{host}" for host in ALLOWED_HOSTS if host not in ['localhost', '127.0.0.1']]

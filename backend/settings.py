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
    ]
}

# ==============================================================================
# 4. CORS CONFIGURATION
# ==============================================================================
from corsheaders.defaults import default_headers
CORS_ALLOW_HEADERS = list(default_headers) + [
    'x-tenant',
    'x-agent-key',
]

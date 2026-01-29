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
    
    # Local Apps
    'core',
    'products',
    'services',

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
        'rest_framework.authentication.SessionAuthentication',  # For Admin Panel
        'rest_framework.authentication.BasicAuthentication',    # For Testing/Scripts
    ],
    
    # Permissions (Safe by default)
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    
    # Pagination & Filtering
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    
    # Error Handling
    'EXCEPTION_HANDLER': 'rest_framework.views.exception_handler',
}

# Add Browsable API only in development
if DEBUG:
    REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ]
else:
    REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
        'rest_framework.renderers.JSONRenderer',
    ]

MIDDLEWARE = [
    # Security & CORS (CorsMiddleware MUST stay at the top)
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    
    # WhiteNoise (must be after SecurityMiddleware)
    'whitenoise.middleware.WhiteNoiseMiddleware',
    
    # Django Core
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
    # Custom Middleware (must be after auth)
    'core.middleware.TenantMiddleware',
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.static',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

# ==============================================================================
# 4. DATABASE - PostgreSQL with connection pooling
# ==============================================================================

DB_NAME = get_env_var('DB_NAME')
DB_USER = get_env_var('DB_USER')
DB_PASSWORD = get_env_var('DB_PASSWORD')
DB_HOST = get_env_var('DB_HOST')
DB_PORT = get_env_var('DB_PORT', '5432')

# Use PostgreSQL if configured, otherwise SQLite for development
if all([DB_NAME, DB_USER, DB_PASSWORD, DB_HOST]):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': DB_NAME,
            'USER': DB_USER,
            'PASSWORD': DB_PASSWORD,
            'HOST': DB_HOST,
            'PORT': DB_PORT,
            'CONN_MAX_AGE': 600,  # 10 minutes connection pooling
            'CONN_HEALTH_CHECKS': True,
            'OPTIONS': {
                'connect_timeout': 10,
            },
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ==============================================================================
# 5. CACHE & REDIS CONFIGURATION
# ==============================================================================

REDIS_PASSWORD = get_env_var('REDIS_PASSWORD', '')
# Use service name 'redis' for Docker internal networking by default
REDIS_URL = get_env_var('REDIS_URL', 'redis://redis:6379/1')

# Determine if we should use Redis
use_redis = not DEBUG or (DB_NAME and DB_HOST and DB_USER and DB_PASSWORD)

if use_redis:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'PASSWORD': REDIS_PASSWORD,
                'SOCKET_CONNECT_TIMEOUT': 5,
                'SOCKET_TIMEOUT': 5,
                'CONNECTION_POOL_KWARGS': {
                    'max_connections': 100,
                    'retry_on_timeout': True
                },
                'SERIALIZER': 'django_redis.serializers.pickle.PickleSerializer',
            },
            'KEY_PREFIX': f'saas_{DJANGO_ENV}',
        }
    }
    
    # Cache-based sessions for performance
    SESSION_ENGINE = "django.contrib.sessions.backends.cache"
    SESSION_CACHE_ALIAS = "default"
else:
    # Local memory cache for development
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
        }
    }
    
    # File-based sessions for development
    SESSION_ENGINE = "django.contrib.sessions.backends.file"
    SESSION_FILE_PATH = BASE_DIR / 'sessions'

# Session configuration
SESSION_COOKIE_NAME = 'saas_sessionid'
SESSION_COOKIE_AGE = 1209600  # 2 weeks
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = 'Lax' if DEBUG else 'Strict'

# CSRF configuration
CSRF_COOKIE_NAME = 'saas_csrftoken'
CSRF_COOKIE_AGE = 31449600  # 1 year
CSRF_COOKIE_HTTPONLY = False  # Must be False for AJAX
CSRF_COOKIE_SECURE = not DEBUG
CSRF_USE_SESSIONS = False

# ==============================================================================
# 6. TENANT CONFIGURATION
# ==============================================================================

TENANT_MODEL = 'core.Tenant'
TENANT_RATE_LIMIT = get_env_var('TENANT_RATE_LIMIT', '100/m')
TENANT_CACHE_TIMEOUT = int(get_env_var('TENANT_CACHE_TIMEOUT', '300'))

# ==============================================================================
# 7. LOGGING CONFIGURATION
# ==============================================================================

LOG_LEVEL = get_env_var('DJANGO_LOG_LEVEL', 'INFO' if not DEBUG else 'DEBUG')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'tenant_context': {
            '()': 'core.logging.TenantContextFilter',
        },
        'request_context': {
            '()': 'core.logging.RequestContextFilter',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
    },
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {tenant} {user}@{ip} {method} {path} {module}: {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {tenant} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'filters': ['tenant_context', 'request_context'],
            'formatter': 'verbose' if DEBUG else 'simple',
        },
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler',
            'include_html': True,
        }
    },
    'loggers': {
        '': {  # Root Logger
            'handlers': ['console'],
            'level': LOG_LEVEL,
        },
        'django': {
            'handlers': ['console', 'mail_admins'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'core': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'propagate': False,
        },
        'django_ratelimit': {
            'handlers': ['console'],
            'level': 'WARNING' if DEBUG else 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# ==============================================================================
# 8. RATE LIMITING & HEALTH CHECK (Requested)
# ==============================================================================

RATELIMIT_ENABLE = True
RATELIMIT_USE_CACHE = 'default'
RATELIMIT_VIEW = 'core.views.RateLimitExceededView'

HEALTH_CHECK = {
    'DATABASE': True,
    'CACHE': True,
    'STORAGE': False,  # Set to True if using S3
}

# JWT Configuration (for future use)
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_DELTA = 3600  # 1 hour

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# ==============================================================================
# 9. INTERNATIONALIZATION & STATIC FILES
# ==============================================================================

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# WhiteNoise configuration - only in production
if not DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
    WHITENOISE_MAX_AGE = 31536000  # 1 year cache for static files
    WHITENOISE_AUTOREFRESH = False
else:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# File upload limits
FILE_UPLOAD_MAX_MEMORY_SIZE = 26214400  # 25MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 26214400  # 25MB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# ==============================================================================
# 10. CORS & HTTPS HARDENING
# ==============================================================================

# Parse CORS origins into a proper Python list
cors_origins_str = get_env_var('CORS_ALLOWED_ORIGINS', '')
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in cors_origins_str.split(',') if origin.strip()]

# CORS settings
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ['DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT']

# Explicitly allow X-Tenant header for multi-tenancy support
from corsheaders.defaults import default_headers
CORS_ALLOW_HEADERS = list(default_headers) + [
    'x-tenant',
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
        CORS_ALLOWED_ORIGINS = [
            f"https://{host}" for host in ALLOWED_HOSTS 
            if host and host not in ['localhost', '127.0.0.1', 'backend']
        ]
    
    # HTTPS hardening (Production only)
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    
    # Trust proxy headers from Nginx Proxy Manager
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    
    # CSRF trusted origins (Must match the list format)
    CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS.copy()
    
    # Additional security for production
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'
    REFERRER_POLICY = 'same-origin'

# ==============================================================================
# 11. EMAIL & ADMIN SETTINGS
# ==============================================================================

# Email configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend' if not DEBUG else 'django.core.mail.backends.console.EmailBackend'
EMAIL_HOST = get_env_var('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(get_env_var('EMAIL_PORT', '587'))
EMAIL_HOST_USER = get_env_var('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = get_env_var('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = get_env_var('EMAIL_USE_TLS', 'True') == 'True'
DEFAULT_FROM_EMAIL = get_env_var('DEFAULT_FROM_EMAIL', 'webmaster@localhost')
SERVER_EMAIL = get_env_var('SERVER_EMAIL', 'root@localhost')

# Admin emails for error reporting
ADMINS = [
    ('Admin', get_env_var('ADMIN_EMAIL', 'admin@franciscodes.com')),
]

# ==============================================================================
# 12. ADDITIONAL SETTINGS
# ==============================================================================

# Default auto field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Admin URL
ADMIN_URL = 'admin/'

# File storage
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# CSRF failure view
CSRF_FAILURE_VIEW = 'core.views.csrf_failure'

# Custom e-commerce settings
ECOMMERCE = {
    'DEFAULT_CURRENCY': 'USD',
    'DEFAULT_TAX_RATE': 0.20,  # 20% VAT
    'SHIPPING_ENABLED': True,
    'REVIEWS_REQUIRE_APPROVAL': True,
    'LOW_STOCK_THRESHOLD': 5,
}
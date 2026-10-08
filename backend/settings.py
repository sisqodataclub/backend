"""
Django settings for backend project.
"""
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================================================
# HVT Authentication Configuration
# ============================================================================
HVT_BASE_URL = os.getenv('HVT_BASE_URL', 'https://auth.franciscodes.com/api/v1')
HVT_API_KEY = os.getenv('HVT_API_KEY')  # Must be set in .env

# ============================================================================
# Core Settings
# ============================================================================
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-m7_-fo@qfi@=r%3hqocvzu86_d1um)xrp=pgs13kncua0=6xq$')
DEBUG = os.getenv('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = ["*"]

cors_env = os.getenv("CORS_ALLOWED_ORIGINS", "")
csrf_env = os.getenv("CSRF_TRUSTED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in cors_env.split(",")] if cors_env else []
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in csrf_env.split(",")] if csrf_env else []

# ============================================================================
# Authentication Backends
# ============================================================================
AUTHENTICATION_BACKENDS = [
    'backend.authentication.HVTJWTBackend',   # Custom HVT JWT validation
    'django.contrib.auth.backends.ModelBackend',  # Fallback for admin
]

# ============================================================================
# Django REST Framework
# ============================================================================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        'backend.authentication.HVTJWTBackend',  # Primary: HVT JWT
        # REMOVED: rest_framework_simplejwt.authentication.JWTAuthentication
        "rest_framework.authentication.SessionAuthentication",  # For admin
    ),
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 6,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'booking_limit': '5/hour',
        'contact_limit': '10/hour'
    }
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ============================================================================
# Email Configuration
# ============================================================================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS") == "True"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL")

if not DEFAULT_FROM_EMAIL:
    DEFAULT_FROM_EMAIL = 'noreply@pdfconverter.com'

# ============================================================================
# Application Definition
# ============================================================================
INSTALLED_APPS = [
    'daphne',
    'channels',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "api",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "cv",
    'pdf_converter',       # PDF Converter app
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'
ASGI_APPLICATION = 'backend.asgi.application'

# ============================================================================
# Database
# ============================================================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db' / 'db.sqlite3',
    }
}

# ============================================================================
# Password Validation
# ============================================================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ============================================================================
# Internationalization
# ============================================================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ============================================================================
# Static Files
# ============================================================================
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOW_CREDENTIALS = True
# Allow custom headers (including X-API-Key for PDF converter)
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-api-key',
    'x-agent-key',
]










# ============================================================================
# Celery & RabbitMQ
# ============================================================================
CELERY_BROKER_URL = 'amqp://guest:guest@rabbitmq:5672//'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'

# ============================================================================
# Cache
# ============================================================================
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': os.path.join(BASE_DIR, 'shared_cache'),
    }
}

# ============================================================================
# WebSockets (Channels)
# ============================================================================
REDIS_HOST = os.getenv("REDIS_HOST", "franciscodes-redis")
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [(REDIS_HOST, 6379)],
        },
    },
}

# ============================================================================
# PDF Converter Configuration
# ============================================================================

# --- Frontend Authentication (Magic Link) ---
LOGIN_URL = '/pdf/login/'
LOGIN_REDIRECT_URL = '/pdf/'

# Session lifetime: 7 days (604800 seconds)
SESSION_COOKIE_AGE = 604800
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True

# --- External API Authentication (API Keys) ---
# List of valid API keys for external apps (machine-to-machine)
# Get from environment variable: PDF_API_KEYS=key1,key2,key3
PDF_API_KEYS = os.getenv('PDF_API_KEYS', '').split(',')

# If no keys are set in .env, use these development defaults
if not PDF_API_KEYS or PDF_API_KEYS == ['']:
    PDF_API_KEYS = [
        'dev-api-key-12345',
        'test-api-key-67890'
    ]

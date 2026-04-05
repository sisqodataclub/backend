# core/middleware.py
import jwt
import logging
from django.conf import settings
from django.http import JsonResponse
from django.db.models import Q
from django.core.cache import cache
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited

# ✅ CRITICAL: Import thread-local utilities from utils
from .utils import get_current_tenant, set_current_tenant, set_current_request, clear_thread_locals
from .models import Tenant

logger = logging.getLogger(__name__)


class TenantMiddleware:
    """
    Multi-tenant middleware with security fixes.
    Uses thread-local storage from core.utils to share state with models.
    """

    EXEMPT_PATHS = [
        '/admin/',
        '/static/',
        '/media/',
        '/health/',
        '/api/auth/',
        '/api/schema/',
        '/api/docs/',
    ]

    def __init__(self, get_response):
        self.get_response = get_response
        self.rate_limit_config = getattr(settings, 'TENANT_RATE_LIMIT', '100/m')

    def __call__(self, request):
        set_current_request(request)

        if self._is_exempt_path(request.path):
            request.tenant = None
            set_current_tenant(None)
            response = self.get_response(request)
            clear_thread_locals()
            return response

        try:
            self._apply_rate_limiting(request)
        except Ratelimited:
            response = JsonResponse({
                "detail": "Too many tenant identification attempts. Please try again later.",
                "code": "rate_limit_exceeded"
            }, status=429)
            clear_thread_locals()
            return response

        tenant = None
        detection_method = None

        if 'Authorization' in request.headers:
            tenant, detection_method = self._get_tenant_from_jwt(request)

        if not tenant:
            tenant_name = request.headers.get('X-Tenant')
            if tenant_name:
                tenant, detection_method = self._get_tenant_by_name(tenant_name)

        if not tenant:
            host = request.get_host().split(':')[0]
            tenant, detection_method = self._get_tenant_by_domain(host)

        if not tenant:
            logger.warning(
                f"Tenant not found for {request.method} {request.path}",
                extra={
                    'ip': self._get_client_ip(request),
                    'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                    'x_tenant': request.headers.get('X-Tenant'),
                    'host': request.get_host(),
                }
            )
            response = self._tenant_not_found_response(request)
            clear_thread_locals()
            return response

        if not tenant.is_active:
            logger.warning(
                f"Inactive tenant attempted access: {tenant.name}",
                extra={'tenant_id': tenant.id, 'path': request.path}
            )
            response = JsonResponse({
                "detail": "Tenant account is inactive.",
                "code": "tenant_inactive"
            }, status=403)
            clear_thread_locals()
            return response

        request.tenant = tenant
        set_current_tenant(tenant)

        request.META['TENANT_ID'] = str(tenant.id)
        request.META['TENANT_NAME'] = tenant.name

        logger.debug(
            f"Tenant identified: {tenant.name} via {detection_method}",
            extra={
                'tenant_id': tenant.id,
                'detection_method': detection_method,
                'path': request.path
            }
        )

        try:
            response = self.get_response(request)
            self._add_security_headers(response)
            return response
        finally:
            clear_thread_locals()

    def _is_exempt_path(self, path):
        return any(path.startswith(exempt) for exempt in self.EXEMPT_PATHS)

    def _apply_rate_limiting(self, request):
        @ratelimit(key='ip', rate=self.rate_limit_config, method='ALL')
        def rate_limit_check(req):
            return None
        rate_limit_check(request)

    def _get_tenant_by_name(self, tenant_name):
        cache_key = f'tenant:name:{tenant_name}'
        tenant = cache.get(cache_key)

        if tenant is None:
            tenant = Tenant.objects.filter(
                name=tenant_name,
                is_active=True
            ).select_related().first()

            if tenant:
                cache.set(cache_key, tenant, settings.TENANT_CACHE_TIMEOUT)
            else:
                cache.set(cache_key, False, 60)
                return None, None

        return (tenant, 'header') if tenant else (None, None)

    def _get_tenant_by_domain(self, host):
        cache_key = f'tenant:domain:{host}'
        tenant = cache.get(cache_key)

        if tenant is None:
            parts = host.split('.')
            subdomain = parts[0] if len(parts) >= 2 else None

            query = Q(domain=host, is_active=True)
            if subdomain and subdomain != 'www':
                query |= Q(name=subdomain, is_active=True)

            tenant = Tenant.objects.filter(query).select_related().first()

            if tenant:
                cache.set(cache_key, tenant, settings.TENANT_CACHE_TIMEOUT)
            else:
                cache.set(cache_key, False, 60)
                return None, None

        return (tenant, 'domain') if tenant else (None, None)

    def _get_tenant_from_jwt(self, request):
        """Get tenant from JWT with secure dual-signature verification (HS256 & RS256)"""
        auth_header = request.headers.get('Authorization', '')

        if not auth_header.startswith("Bearer "):
            return None, None

        token = auth_header.split(" ")[1]

        try:
            # 1. PEEK at the header to determine the signature type
            unverified_header = jwt.get_unverified_header(token)
            algorithm = unverified_header.get('alg')

            if algorithm == 'RS256':
                # CLERK DASHBOARD (Asymmetric)
                from jwt import PyJWKClient
                clerk_url = getattr(settings, 'CLERK_JWKS_URL', '')
                if not clerk_url:
                    logger.error("CLERK_JWKS_URL is missing in settings")
                    return None, None
                    
                jwks_client = PyJWKClient(clerk_url)
                signing_key = jwks_client.get_signing_key_from_jwt(token)
                
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    options={"verify_aud": False}
                )

            elif algorithm == 'HS256':
                # LIVE E-COMMERCE (Symmetric)
                payload = jwt.decode(
                    token,
                    settings.SECRET_KEY,  
                    algorithms=["HS256"],
                    options={
                        "require": ["exp", "iat"],
                        "verify_exp": True,
                        "verify_iat": True,
                    }
                )
            else:
                logger.error(f"Unsupported JWT algorithm: {algorithm}")
                return None, None

            # 2. Extract tenant
            tenant_identifier = payload.get("tenant")
            if not tenant_identifier:
                return None, None

            cache_key = f'tenant:jwt:{tenant_identifier}'
            tenant = cache.get(cache_key)

            if tenant is None:
                tenant = Tenant.objects.filter(
                    Q(name=tenant_identifier) | Q(domain=tenant_identifier),
                    is_active=True
                ).select_related().first()

                if tenant:
                    cache.set(cache_key, tenant, settings.TENANT_CACHE_TIMEOUT)
                else:
                    cache.set(cache_key, False, 60)
                    return None, None

            return tenant, 'jwt' if tenant else None

        except jwt.ExpiredSignatureError:
            return None, None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT Token: {str(e)}")
            return None, None
        except Exception as e:
            logger.error(f"JWT processing error: {str(e)}")
            return None, None

    def _tenant_not_found_response(self, request):
        error_data = {
            "detail": "Unable to identify tenant. Please check your domain, X-Tenant header, or authentication token.",
            "code": "tenant_not_found"
        }

        if settings.DEBUG:
            error_data["debug"] = {
                "received_host": request.get_host(),
                "x_tenant_header": request.headers.get('X-Tenant'),
                "has_auth_header": 'Authorization' in request.headers
            }

        return JsonResponse(error_data, status=403)

    def _add_security_headers(self, response):
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'

        tenant = get_current_tenant()
        if tenant:
            response['X-Tenant-ID'] = str(tenant.id)

        if not settings.DEBUG:
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
            response['Content-Security-Policy'] = "default-src 'self'"

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip or 'unknown'

import jwt
from django.conf import settings
from django.contrib.auth.models import User
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

class ClerkAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')

        # If there's no Bearer token, let DRF try the next auth method
        if not auth_header or not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ')[1]

        try:
            # 1. Fetch dynamic public keys from your Clerk JWKS URL
            jwks_client = jwt.PyJWKClient(settings.CLERK_JWKS_URL)
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            # 2. Decode and verify the token securely
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={"verify_aud": False}
            )

            # 3. Map the Clerk User ID ('sub') to a Django User
            clerk_user_id = payload.get('sub')
            user, created = User.objects.get_or_create(username=clerk_user_id)

            return (user, token)

        except Exception as e:
            raise AuthenticationFailed(f"Clerk Auth Failed: {str(e)}")

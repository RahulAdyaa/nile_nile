"""
JWT Cookie Authentication Middleware

Reads JWT access/refresh tokens from httpOnly cookies and authenticates
the user on every request. Auto-refreshes expired access tokens silently.

This replaces Django's session-based auth for browser views while keeping
the same @login_required decorator working seamlessly.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from django.conf import settings

User = get_user_model()

ACCESS_COOKIE = 'nile_access'
REFRESH_COOKIE = 'nile_refresh'


class JWTCookieAuthMiddleware:
    """
    Middleware that authenticates users via JWT tokens stored in httpOnly cookies.
    Runs after Django's AuthenticationMiddleware so request.user exists.
    If a valid JWT cookie is found, it overrides the session-based user.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip if user is already authenticated via session (e.g., admin, allauth)
        if hasattr(request, 'user') and request.user.is_authenticated:
            return self.get_response(request)

        access_token = request.COOKIES.get(ACCESS_COOKIE)
        refresh_token = request.COOKIES.get(REFRESH_COOKIE)
        new_access = None

        if access_token:
            user = self._get_user_from_token(access_token)
            if user:
                request.user = user
                return self.get_response(request)

        # Access token missing or expired — try refresh
        if refresh_token:
            user, new_access = self._refresh_access_token(refresh_token)
            if user:
                request.user = user

        response = self.get_response(request)

        # Set the new access token cookie if we refreshed
        if new_access:
            self._set_access_cookie(response, new_access)

        return response

    @staticmethod
    def _get_user_from_token(token_str):
        """Validate access token and return the user."""
        try:
            token = AccessToken(token_str)
            user_id = token.get('user_id')
            return User.objects.get(id=user_id)
        except (TokenError, InvalidToken, User.DoesNotExist):
            return None

    @staticmethod
    def _refresh_access_token(refresh_str):
        """Use refresh token to generate a new access token. Returns (user, new_access_str)."""
        try:
            refresh = RefreshToken(refresh_str)
            user_id = refresh.get('user_id')
            user = User.objects.get(id=user_id)
            # Generate new access token
            new_access = str(refresh.access_token)
            return user, new_access
        except (TokenError, InvalidToken, User.DoesNotExist):
            return None, None

    @staticmethod
    def _set_access_cookie(response, access_token):
        """Set the refreshed access token cookie on the response."""
        from datetime import timedelta
        max_age = int(settings.SIMPLE_JWT.get(
            'ACCESS_TOKEN_LIFETIME', timedelta(hours=2)
        ).total_seconds())
        response.set_cookie(
            ACCESS_COOKIE,
            access_token,
            max_age=max_age,
            httponly=True,
            samesite='Lax',
            secure=not settings.DEBUG,
            path='/',
        )


def set_jwt_cookies(response, user):
    """
    Helper to set both access and refresh JWT cookies on a response.
    Call this from login views.
    """
    from datetime import timedelta
    refresh = RefreshToken.for_user(user)
    access = str(refresh.access_token)

    access_max_age = int(settings.SIMPLE_JWT.get(
        'ACCESS_TOKEN_LIFETIME', timedelta(hours=2)
    ).total_seconds())
    refresh_max_age = int(settings.SIMPLE_JWT.get(
        'REFRESH_TOKEN_LIFETIME', timedelta(days=7)
    ).total_seconds())

    secure = not settings.DEBUG

    response.set_cookie(
        ACCESS_COOKIE, access,
        max_age=access_max_age,
        httponly=True, samesite='Lax', secure=secure, path='/',
    )
    response.set_cookie(
        REFRESH_COOKIE, str(refresh),
        max_age=refresh_max_age,
        httponly=True, samesite='Lax', secure=secure, path='/',
    )
    return response


def clear_jwt_cookies(response):
    """Remove both JWT cookies on logout."""
    response.delete_cookie(ACCESS_COOKIE, path='/')
    response.delete_cookie(REFRESH_COOKIE, path='/')
    return response

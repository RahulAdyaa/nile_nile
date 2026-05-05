from django.contrib.auth import get_user_model, authenticate, login, logout
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    RegisterSerializer,
    NileTokenObtainPairSerializer,
    UserProfileSerializer,
)
from .middleware import set_jwt_cookies, clear_jwt_cookies

User = get_user_model()


# ─── API AUTH VIEWS ──────────────────────────────────────────────────────────

class NileTokenObtainView(TokenObtainPairView):
    """POST /api/auth/token/ — Returns access + refresh tokens with user metadata."""
    serializer_class = NileTokenObtainPairSerializer


@api_view(['POST'])
@permission_classes([AllowAny])
def api_register(request):
    """POST /api/auth/register/ — Create a new analyst account via the API."""
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        # Immediately issue tokens so the client can log in without a second request
        refresh = RefreshToken.for_user(user)
        return Response({
            'message': 'User registered successfully.',
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_logout(request):
    """POST /api/auth/logout/ — Blacklist the provided refresh token (server-side revocation)."""
    try:
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'error': 'Refresh token is required.'}, status=status.HTTP_400_BAD_REQUEST)
        token = RefreshToken(refresh_token)
        token.blacklist()
        return Response({'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_me(request):
    """GET /api/auth/me/ — Return the authenticated user's profile."""
    serializer = UserProfileSerializer(request.user)
    return Response(serializer.data)


# ─── BROWSER / SESSION AUTH VIEWS ────────────────────────────────────────────

def browser_login(request):
    """Session + JWT cookie login for the HTML dashboard."""
    if request.user.is_authenticated:
        return redirect('dashboard_home')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            next_url = request.GET.get('next', '/')
            response = redirect(next_url)
            set_jwt_cookies(response, user)
            return response
        else:
            messages.error(request, 'Invalid credentials. Please try again.')

    return render(request, 'accounts/login.html')


def browser_register(request):
    """Session-based registration for the HTML dashboard."""
    if request.user.is_authenticated:
        return redirect('dashboard_home')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')

        if password != password2:
            messages.error(request, 'Passwords do not match.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken.')
        elif User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered.')
        else:
            user = User.objects.create_user(username=username, email=email, password=password)
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f'Welcome, {user.username}! Your analyst account is active.')
            response = redirect('dashboard_home')
            set_jwt_cookies(response, user)
            return response

    return render(request, 'accounts/register.html')


def browser_logout(request):
    """Session + JWT cookie logout."""
    logout(request)
    messages.info(request, 'You have been securely signed out.')
    response = redirect('auth_login')
    clear_jwt_cookies(response)
    return response

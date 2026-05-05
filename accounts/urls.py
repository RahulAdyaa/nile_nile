from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # ─── Browser (Session) Routes ─────────────────────────────────────────────
    path('login/', views.browser_login, name='auth_login'),
    path('register/', views.browser_register, name='auth_register'),
    path('logout/', views.browser_logout, name='auth_logout'),

    # ─── JWT API Routes ───────────────────────────────────────────────────────
    path('api/auth/register/', views.api_register, name='api_register'),
    path('api/auth/token/', views.NileTokenObtainView.as_view(), name='api_token_obtain'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='api_token_refresh'),
    path('api/auth/logout/', views.api_logout, name='api_logout'),
    path('api/auth/me/', views.api_me, name='api_me'),
]

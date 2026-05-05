from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Extended user model with role-based access control.
    Roles:
      - admin:   Full access (upload data, trigger pipelines, view all dashboards)
      - analyst: View-only access to analytics dashboards
    """
    ROLE_ADMIN = 'admin'
    ROLE_ANALYST = 'analyst'

    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Administrator'),
        (ROLE_ANALYST, 'Analyst'),
    ]

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_ANALYST,
        help_text='Determines what platform features this user can access.'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    @property
    def is_admin_user(self):
        return self.role == self.ROLE_ADMIN or self.is_superuser

    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'

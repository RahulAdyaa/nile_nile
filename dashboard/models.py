from django.db import models
from django.db.models import Q
from django.conf import settings


# ─── Analysis Session ─────────────────────────────────────────────────────────

class AnalysisSession(models.Model):
    name = models.CharField(max_length=255, default='Untitled Analysis')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='analysis_sessions')
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    MAX_SESSIONS_PER_USER = 10

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        status = "Active" if self.is_active else "Archived"
        return f"{self.name} ({status}) — {self.created_at:%Y-%m-%d %H:%M}"

    def archive(self):
        self.is_active = False
        self.save(update_fields=['is_active', 'updated_at'])

    def activate(self):
        # Deactivate all other sessions for this user
        AnalysisSession.objects.filter(user=self.user, is_active=True).update(is_active=False)
        self.is_active = True
        self.save(update_fields=['is_active', 'updated_at'])

    @classmethod
    def get_active_session(cls, user):
        return cls.objects.filter(user=user, is_active=True).first()

    @classmethod
    def create_new_session(cls, user, name=None):
        # Archive current active session
        cls.objects.filter(user=user, is_active=True).update(is_active=False)
        # Auto-name
        if not name:
            count = cls.objects.filter(user=user).count() + 1
            name = f"Analysis #{count}"
        session = cls.objects.create(user=user, name=name, is_active=True)
        # Enforce session limit — delete oldest archived sessions
        cls._enforce_limit(user)
        return session

    @classmethod
    def _enforce_limit(cls, user):
        sessions = cls.objects.filter(user=user).order_by('-updated_at')
        if sessions.count() > cls.MAX_SESSIONS_PER_USER:
            to_delete = sessions[cls.MAX_SESSIONS_PER_USER:]
            for s in to_delete:
                s.delete()  # CASCADE deletes related Customer/Product/Sale


class Customer(models.Model):
    session = models.ForeignKey(AnalysisSession, on_delete=models.CASCADE, related_name='customers', null=True, blank=True)
    customer_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=100, db_index=True)
    city = models.CharField(max_length=100)

    age = models.IntegerField(null=True, blank=True)
    gender = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        unique_together = ('session', 'name', 'region', 'city')
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'customer_id'],
                condition=Q(customer_id__isnull=False) & ~Q(customer_id=''),
                name='unique_customer_id_per_session',
            ),
        ]

    def __str__(self):
        return self.name


class Product(models.Model):
    session = models.ForeignKey(AnalysisSession, on_delete=models.CASCADE, related_name='products', null=True, blank=True)
    product_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100, db_index=True)
    sub_category = models.CharField(max_length=100)

    class Meta:
        unique_together = ('session', 'name', 'category', 'sub_category')
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'product_id'],
                condition=Q(product_id__isnull=False) & ~Q(product_id=''),
                name='unique_product_id_per_session',
            ),
        ]

    def __str__(self):
        return self.name


class Sale(models.Model):
    session = models.ForeignKey(AnalysisSession, on_delete=models.CASCADE, related_name='sales', null=True, blank=True)
    order_id = models.CharField(max_length=50)
    order_date = models.DateField(db_index=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='sales')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='sales')
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total_sales = models.DecimalField(max_digits=15, decimal_places=2)
    profit = models.DecimalField(max_digits=15, decimal_places=2)
    payment_mode = models.CharField(max_length=100)
    delivery_time_days = models.IntegerField(null=True, blank=True)
    returned = models.BooleanField(default=False)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_flagged = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['session', 'order_date']),
            models.Index(fields=['order_date', 'customer']),
            models.Index(fields=['customer', 'total_sales']),
            models.Index(fields=['product', 'total_sales']),
            models.Index(fields=['order_date', 'total_sales', 'profit']),
        ]

    def __str__(self):
        return f"Order {self.order_id} - {self.product.name}"


# ─── Data Upload Tracking ────────────────────────────────────────────────────

class DataUpload(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    ]

    session = models.ForeignKey(AnalysisSession, on_delete=models.CASCADE, related_name='uploads', null=True, blank=True)
    file = models.FileField(upload_to='uploads/%Y/%m/')
    original_filename = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='uploads')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    rows_processed = models.IntegerField(default=0)
    column_mapping = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default='')
    processing_time_ms = models.IntegerField(default=0)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.original_filename} ({self.get_status_display()})"


# ─── Audit Log ────────────────────────────────────────────────────────────────

class AuditLog(models.Model):
    ACTION_LOGIN = 'login'
    ACTION_LOGOUT = 'logout'
    ACTION_UPLOAD = 'upload'
    ACTION_ETL_TRIGGER = 'etl_trigger'
    ACTION_EXPORT = 'export'
    ACTION_REGISTER = 'register'

    ACTION_CHOICES = [
        (ACTION_LOGIN, 'User Login'),
        (ACTION_LOGOUT, 'User Logout'),
        (ACTION_UPLOAD, 'Data Upload'),
        (ACTION_ETL_TRIGGER, 'ETL Pipeline Triggered'),
        (ACTION_EXPORT, 'Report Exported'),
        (ACTION_REGISTER, 'User Registration'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    detail = models.TextField(blank=True, default='')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.get_action_display()} by {self.user}"

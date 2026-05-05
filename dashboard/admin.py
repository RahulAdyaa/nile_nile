from django.contrib import admin
from .models import Customer, Product, Sale, DataUpload, AuditLog

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'region', 'city', 'age', 'gender')
    search_fields = ('name', 'region', 'city')
    list_filter = ('region', 'city', 'gender')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'sub_category')
    search_fields = ('name', 'category', 'sub_category')
    list_filter = ('category', 'sub_category')

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'customer', 'product', 'quantity', 'total_sales', 'order_date')
    search_fields = ('order_id', 'customer__name', 'product__name')
    list_filter = ('order_date', 'payment_mode', 'returned')
    date_hierarchy = 'order_date'

@admin.register(DataUpload)
class DataUploadAdmin(admin.ModelAdmin):
    list_display = ('original_filename', 'uploaded_by', 'status', 'uploaded_at', 'rows_processed')
    list_filter = ('status', 'uploaded_at')
    search_fields = ('original_filename', 'uploaded_by__username')

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'timestamp', 'ip_address')
    list_filter = ('action', 'timestamp')
    search_fields = ('user__username', 'detail')
    readonly_fields = ('timestamp', 'ip_address')

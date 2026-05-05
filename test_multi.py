"""Test the multi-file pipeline and export combined result."""
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'
import django
django.setup()

import pandas as pd
from dashboard.etl.pipeline import ETLPipeline
from dashboard.models import AnalysisSession, Customer, Product, Sale
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.core.cache import cache

User = get_user_model()
user = User.objects.filter(email='rahuladyayt@gmail.com').first()

session = AnalysisSession.create_new_session(user, name='Multi-File Combined')
print(f"Session #{session.id}")

# Use run_multi to combine both files
pipeline = ETLPipeline.run_multi(
    file_configs=[
        {'file_path': 'data/sales_transactions.csv'},
        {'file_path': 'data/order_details.csv'},
    ],
    session_id=session.id,
    wipe_existing=True,
)

# Stats
agg = Sale.objects.filter(session=session).aggregate(
    rev=Sum('total_sales'), prof=Sum('profit'))
rev = float(agg['rev'] or 0)
prof = float(agg['prof'] or 0)

print(f"\n{'='*60}")
print(f"RESULTS")
print(f"{'='*60}")
print(f"  Customers: {Customer.objects.filter(session=session).count()}")
print(f"  Products:  {Product.objects.filter(session=session).count()}")
print(f"  Sales:     {Sale.objects.filter(session=session).count()}")
print(f"  Revenue:   ${rev:,.2f}")
print(f"  Profit:    ${prof:,.2f}")
print(f"  Margin:    {prof/rev*100:.1f}%")

# Export combined data for user to inspect
qs = Sale.objects.filter(session=session).select_related('customer', 'product')
rows = []
for s in qs.iterator():
    rows.append({
        'Order ID': s.order_id,
        'Order Date': s.order_date,
        'Customer ID': s.customer.customer_id or '',
        'Customer Name': s.customer.name,
        'Region': s.customer.region,
        'City': s.customer.city,
        'Age': s.customer.age or '',
        'Gender': s.customer.gender or '',
        'Product ID': s.product.product_id or '',
        'Product Name': s.product.name,
        'Category': s.product.category,
        'Quantity': s.quantity,
        'Unit Price': float(s.unit_price),
        'Discount': float(s.discount),
        'Revenue': float(s.total_sales),
        'Profit': float(s.profit),
        'Payment Mode': s.payment_mode,
        'Delivery Days': s.delivery_time_days or '',
    })

df = pd.DataFrame(rows)
df.to_csv('data/combined_output.csv', index=False)
print(f"\nExported {len(df)} rows → data/combined_output.csv")

# Show a TXN row (from file 1) to prove it has region/city from file 2
txn_row = df[df['Order ID'].str.startswith('TXN')].head(1)
print(f"\nSample TXN row (from file 1, enriched with file 2 data):")
print(txn_row.to_string())

cache.clear()

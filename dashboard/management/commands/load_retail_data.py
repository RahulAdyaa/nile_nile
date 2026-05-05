import pandas as pd
from django.core.management.base import BaseCommand
from dashboard.models import Transaction
from django.utils.timezone import make_aware
from datetime import datetime

class Command(BaseCommand):
    help = 'Load online retail data from Excel file'

    def handle(self, *args, **kwargs):
        file_path = 'data/online_retail_II.xlsx'
        self.stdout.write(self.style.SUCCESS(f'Reading data from {file_path}...'))
        
        # Retail data has two sheets usually
        xls = pd.ExcelFile(file_path)
        sheets = xls.sheet_names
        
        all_transactions = []
        
        for sheet in sheets:
            self.stdout.write(f'Processing sheet: {sheet}')
            df = pd.read_excel(xls, sheet_name=sheet)
            
            # Clean column names (strip spaces)
            df.columns = [c.strip() for c in df.columns]
            
            # Subsample for prototype if too large (let's take 5000 per sheet for now)
            df = df.head(5000)
            
            for index, row in df.iterrows():
                try:
                    # InvoiceDate can be a Timestamp object from pandas
                    inv_date = row['InvoiceDate']
                    if pd.isna(inv_date):
                        continue
                        
                    # Handle price/quantity issues
                    try:
                        price = float(row['Price'])
                        qty = int(row['Quantity'])
                    except (ValueError, TypeError):
                        continue

                    transaction = Transaction(
                        invoice=str(row['Invoice']),
                        stock_code=str(row['StockCode']),
                        description=str(row['Description']) if not pd.isna(row['Description']) else "",
                        quantity=qty,
                        invoice_date=inv_date if inv_date.tzinfo else make_aware(inv_date),
                        price=price,
                        customer_id=str(int(row['Customer ID'])) if not pd.isna(row['Customer ID']) else None,
                        country=str(row['Country'])
                    )
                    all_transactions.append(transaction)
                    
                    if len(all_transactions) >= 1000:
                        Transaction.objects.bulk_create(all_transactions)
                        all_transactions = []
                        self.stdout.write(self.style.SUCCESS(f'Bulk created 1000 records...'))
                        
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Row {index} skipped: {e}'))
        
        if all_transactions:
            Transaction.objects.bulk_create(all_transactions)
            
        self.stdout.write(self.style.SUCCESS('Data loading complete!'))

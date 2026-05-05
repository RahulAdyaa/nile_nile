import os
from django.core.management.base import BaseCommand
from dashboard.etl.pipeline import ETLPipeline
from django.conf import settings

class Command(BaseCommand):
    help = 'Ingest E-commerce sales data using the robust ETL pipeline'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, help='Path to the CSV/Excel file')

    def handle(self, *args, **options):
        file_path = options['file']
        
        if not file_path:
            # Try to find the file in the default project location
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            parent_dir = os.path.dirname(base_dir)
            file_path = os.path.join(parent_dir, 'Ecommerce_Sales_Data_2024_2025.csv')
            
        if not os.path.exists(file_path):
            self.stderr.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        self.stdout.write(self.style.SUCCESS(f"Initializing Ingestion for: {file_path}"))
        
        try:
            pipeline = ETLPipeline(file_path)
            pipeline.run()
            self.stdout.write(self.style.SUCCESS("Data ingestion completed successfully."))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Ingestion Failed: {str(e)}"))

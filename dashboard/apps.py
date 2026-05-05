from django.apps import AppConfig
import threading


class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dashboard'

    def ready(self):
        import os

        # Only run auto-ingest in the main process (not the reloader child)
        if os.environ.get('RUN_MAIN') != 'true':
            return

        def auto_ingest():
            try:
                from django.conf import settings
                from django.db import connection
                from dashboard.models import Sale
                from dashboard.etl.pipeline import ETLPipeline

                # Only ingest if DB is empty
                if Sale.objects.exists():
                    connection.close()
                    return

                nile_file = os.path.join(settings.BASE_DIR, 'data', 'online_retail_II.xlsx')
                if not os.path.exists(nile_file):
                    print("[Nile] Auto-ingest skipped: online_retail_II.xlsx not found in data/")
                    connection.close()
                    return

                print("[Nile] No sales data found — auto-ingesting online_retail_II.xlsx ...")
                pipeline = ETLPipeline(nile_file)
                pipeline.run(wipe_existing=False)
                print(f"[Nile] Auto-ingest complete: {len(pipeline.final_df)} records loaded.")
            except Exception as e:
                print(f"[Nile] Auto-ingest failed: {e}")
            finally:
                from django.db import connection
                connection.close()

        threading.Thread(target=auto_ingest, daemon=True).start()

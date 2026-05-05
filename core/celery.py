import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('nile_analytics')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# ─── Periodic Tasks (Cron Jobs) ──────────────────────────────────────────────
app.conf.beat_schedule = {
    # 1. Daily report export — midnight
    'daily-automated-report': {
        'task': 'dashboard.tasks.scheduled_export_report',
        'schedule': crontab(hour=0, minute=0),
    },
    # 2. Cleanup old uploaded files (>30 days) — daily at 2 AM
    'cleanup-old-uploads': {
        'task': 'dashboard.tasks.cleanup_old_uploads',
        'schedule': crontab(hour=2, minute=0),
    },
    # 3. Mark stuck processing jobs as failed — every 10 minutes
    'mark-stale-uploads': {
        'task': 'dashboard.tasks.mark_stale_uploads',
        'schedule': 600.0,  # every 10 minutes (in seconds)
    },
    # 4. Refresh forecast cache — every 6 hours
    'refresh-forecast-cache': {
        'task': 'dashboard.tasks.refresh_forecast_cache',
        'schedule': crontab(hour='*/6', minute=15),
    },
    # 5. Database cleanup — weekly on Sunday at 3 AM
    'cleanup-old-sessions': {
        'task': 'dashboard.tasks.cleanup_old_sessions',
        'schedule': crontab(hour=3, minute=0, day_of_week='sunday'),
    },
}

from django.apps import AppConfig
import threading


# ─── Human-readable labels for cron tasks ─────────────────────────────────────
CRON_LABELS = {
    'daily-automated-report': 'Daily Report Export',
    'cleanup-old-uploads': 'Cleanup Old Uploads',
    'mark-stale-uploads': 'Mark Stale Uploads',
    'refresh-forecast-cache': 'Refresh Forecast Cache',
    'cleanup-old-sessions': 'Cleanup Old Sessions',
}


class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dashboard'

    def ready(self):
        import os

        # Only run in the main process (not the reloader child)
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

        # ─── In-Process Cron Scheduler ────────────────────────────────────
        self._start_cron_scheduler()

    @staticmethod
    def _start_cron_scheduler():
        """Start a lightweight in-process scheduler that mirrors Celery Beat."""
        import time
        from datetime import datetime

        def _crontab_matches(cron, now):
            """Check if a crontab schedule matches the current time."""
            hour_spec = cron.get('hour', '*')
            if isinstance(hour_spec, str) and hour_spec.startswith('*/'):
                if now.hour % int(hour_spec[2:]) != 0:
                    return False
            elif hour_spec != '*':
                if now.hour != int(hour_spec):
                    return False

            minute_spec = cron.get('minute', '*')
            if isinstance(minute_spec, str) and minute_spec.startswith('*/'):
                if now.minute % int(minute_spec[2:]) != 0:
                    return False
            elif minute_spec != '*':
                if now.minute != int(minute_spec):
                    return False

            dow_spec = cron.get('day_of_week', '*')
            if dow_spec != '*':
                day_map = {
                    'monday': 0, 'tuesday': 1, 'wednesday': 2,
                    'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6,
                }
                target_dow = day_map.get(str(dow_spec).lower(), None)
                if target_dow is None:
                    target_dow = int(dow_spec)
                if now.weekday() != target_dow:
                    return False

            return True

        def _resolve_task(task_path):
            """Import and return the task function from a dotted path."""
            module_path, func_name = task_path.rsplit('.', 1)
            from importlib import import_module
            module = import_module(module_path)
            return getattr(module, func_name)

        def _log_run(task_key, label, status, result_msg, duration_ms):
            """Persist cron job execution to CronLog model."""
            try:
                from dashboard.models import CronLog
                CronLog.objects.create(
                    task_name=task_key,
                    task_label=label,
                    status=status,
                    result=str(result_msg)[:1000],
                    duration_ms=duration_ms,
                )
                # Keep only last 200 logs (auto-prune)
                total = CronLog.objects.count()
                if total > 200:
                    cutoff_id = CronLog.objects.order_by('-executed_at').values_list('id', flat=True)[200]
                    CronLog.objects.filter(id__lt=cutoff_id).delete()
            except Exception as e:
                print(f"[Nile Cron] Failed to log: {e}")

        def _scheduler_loop():
            """Main scheduler loop — checks every 30 seconds."""
            from core.celery import app

            schedule = app.conf.beat_schedule
            if not schedule:
                return

            cron_tasks = []
            interval_tasks = []

            for name, entry in schedule.items():
                task_path = entry['task']
                sched = entry['schedule']

                if hasattr(sched, '_orig_hour'):
                    cron_tasks.append({
                        'name': name,
                        'task': task_path,
                        'hour': str(sched._orig_hour),
                        'minute': str(sched._orig_minute),
                        'day_of_week': str(sched._orig_day_of_week),
                    })
                elif isinstance(sched, (int, float)):
                    interval_tasks.append({
                        'name': name,
                        'task': task_path,
                        'interval': sched,
                        'last_run': 0,
                    })

            task_names = [t['name'] for t in cron_tasks] + [t['name'] for t in interval_tasks]
            print(f"[Nile Cron] Scheduler started — {len(task_names)} tasks: {', '.join(task_names)}")

            last_cron_minute = -1

            while True:
                try:
                    now = datetime.now()
                    current_ts = time.time()

                    # ── Interval-based tasks ──
                    for task_info in interval_tasks:
                        if current_ts - task_info['last_run'] >= task_info['interval']:
                            task_info['last_run'] = current_ts
                            label = CRON_LABELS.get(task_info['name'], task_info['name'])
                            start = time.time()
                            try:
                                fn = _resolve_task(task_info['task'])
                                result = fn()
                                duration = int((time.time() - start) * 1000)
                                _log_run(task_info['name'], label, 'success', result, duration)
                                print(f"[Nile Cron] ✓ {label} → {result}")
                            except Exception as e:
                                duration = int((time.time() - start) * 1000)
                                _log_run(task_info['name'], label, 'failed', str(e), duration)
                                print(f"[Nile Cron] ✗ {label} failed: {e}")
                            finally:
                                from django.db import connection
                                connection.close()

                    # ── Crontab-based tasks ──
                    current_minute = now.hour * 60 + now.minute
                    if current_minute != last_cron_minute:
                        last_cron_minute = current_minute
                        for task_info in cron_tasks:
                            cron_spec = {
                                'hour': task_info['hour'],
                                'minute': task_info['minute'],
                                'day_of_week': task_info['day_of_week'],
                            }
                            if _crontab_matches(cron_spec, now):
                                label = CRON_LABELS.get(task_info['name'], task_info['name'])
                                start = time.time()
                                try:
                                    fn = _resolve_task(task_info['task'])
                                    result = fn()
                                    duration = int((time.time() - start) * 1000)
                                    _log_run(task_info['name'], label, 'success', result, duration)
                                    print(f"[Nile Cron] ✓ {label} → {result}")
                                except Exception as e:
                                    duration = int((time.time() - start) * 1000)
                                    _log_run(task_info['name'], label, 'failed', str(e), duration)
                                    print(f"[Nile Cron] ✗ {label} failed: {e}")
                                finally:
                                    from django.db import connection
                                    connection.close()

                except Exception as e:
                    print(f"[Nile Cron] Scheduler error: {e}")

                time.sleep(30)

        scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
        scheduler_thread.start()

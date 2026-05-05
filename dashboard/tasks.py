from celery import shared_task
import os
from django.conf import settings
from datetime import datetime, timedelta
import pandas as pd
from .models import Sale
from django.core.cache import cache

@shared_task
def scheduled_export_report():
    """
    Automated scheduled task to generate periodic Pandas reports:
    Monthly, Region-wise, and Product-wise breakdowns.
    Exports to Excel and saves to media directory.
    """
    from .models import AnalysisSession

    # Export from all sessions (scheduled task is global)
    sales = Sale.objects.select_related('customer', 'product').all()
    if not sales.exists():
        return "No sales data to export."

    data = list(sales.values(
        'order_date', 'total_sales', 'profit', 
        'customer__region', 'product__category', 'product__name'
    ))
    df = pd.DataFrame(data)
    df['order_date'] = pd.to_datetime(df['order_date'])

    # 1. Monthly Summary
    monthly_df = df.set_index('order_date').resample('ME').agg({
        'total_sales': 'sum',
        'profit': 'sum'
    }).reset_index()

    # 2. Region-wise Breakdown
    region_df = df.groupby('customer__region').agg({
        'total_sales': 'sum',
        'profit': 'sum'
    }).reset_index()

    # 3. Product-wise Breakdown
    product_df = df.groupby(['product__category', 'product__name']).agg({
        'total_sales': 'sum',
        'profit': 'sum'
    }).reset_index()

    # Ensure output directory exists
    reports_dir = os.path.join(settings.BASE_DIR, 'media', 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    
    filename = f"nile_automated_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    filepath = os.path.join(reports_dir, filename)

    # Export to Excel with multiple sheets
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        monthly_df.to_excel(writer, sheet_name='Monthly Summary', index=False)
        region_df.to_excel(writer, sheet_name='Regional Breakdown', index=False)
        product_df.to_excel(writer, sheet_name='Product Breakdown', index=False)
        df.to_excel(writer, sheet_name='Raw Data', index=False)

    return f"Report successfully generated at {filepath}"

@shared_task
def process_data_upload(upload_id, wipe_existing=False):
    """
    Background task to process uploaded data via ETLPipeline.

    Multi-file aware: when this is the LAST pending upload in the session,
    it gathers ALL uploads and runs them through the multi-file pipeline
    (combine → clean → load) so dimensions are merged across files.
    """
    from .models import DataUpload
    from .etl.pipeline import ETLPipeline
    import time
    import traceback

    try:
        upload = DataUpload.objects.get(id=upload_id)
        upload.status = DataUpload.STATUS_PROCESSING
        upload.save()

        start_time = time.time()
        session_id = upload.session_id if upload.session_id else None

        # Check if there are other uploads in this session that are ready
        # (have mappings confirmed = status is pending/processing)
        session_uploads = list(
            DataUpload.objects.filter(
                session_id=session_id,
                status__in=[DataUpload.STATUS_PENDING, DataUpload.STATUS_PROCESSING],
            ).order_by('uploaded_at')
        ) if session_id else []

        # Are there still pending (unmapped) files waiting?
        still_pending = [u for u in session_uploads if u.id != upload.id and u.status == DataUpload.STATUS_PENDING]

        if still_pending:
            # Other files haven't been mapped yet — process this one alone
            pipeline = ETLPipeline(upload.file.path, upload.column_mapping, session_id=session_id)
            pipeline.run(wipe_existing=wipe_existing)
            rows = len(pipeline.final_df) if pipeline.final_df is not None else 0
        else:
            # This is the last file — gather ALL session uploads that need processing
            ready_uploads = [u for u in session_uploads if u.id == upload.id or u.status == DataUpload.STATUS_PROCESSING]

            # Also include any uploads that were already processed (to re-combine)
            already_done = list(
                DataUpload.objects.filter(
                    session_id=session_id,
                    status=DataUpload.STATUS_SUCCESS,
                ).order_by('uploaded_at')
            )

            all_uploads = already_done + ready_uploads
            # Deduplicate by id
            seen = set()
            unique_uploads = []
            for u in all_uploads:
                if u.id not in seen:
                    seen.add(u.id)
                    unique_uploads.append(u)

            if len(unique_uploads) > 1:
                # Multi-file: combine all files, then clean + load once
                file_configs = [
                    {'file_path': u.file.path, 'column_mapping': u.column_mapping or {}}
                    for u in unique_uploads
                ]
                pipeline = ETLPipeline.run_multi(
                    file_configs, session_id, wipe_existing=True
                )
                rows = len(pipeline.final_df) if pipeline.final_df is not None else 0
            else:
                # Single file
                pipeline = ETLPipeline(upload.file.path, upload.column_mapping, session_id=session_id)
                pipeline.run(wipe_existing=wipe_existing)
                rows = len(pipeline.final_df) if pipeline.final_df is not None else 0

        upload.status = DataUpload.STATUS_SUCCESS
        upload.rows_processed = rows
        upload.processing_time_ms = int((time.time() - start_time) * 1000)
        upload.save()

        # Mark any other processing uploads as success too
        DataUpload.objects.filter(
            session_id=session_id,
            status=DataUpload.STATUS_PROCESSING,
        ).exclude(id=upload.id).update(
            status=DataUpload.STATUS_SUCCESS,
            rows_processed=rows,
        )

        cache.clear()
        return "Success"
    except Exception as e:
        upload.status = DataUpload.STATUS_FAILED
        upload.error_message = f"{str(e)}\n{traceback.format_exc()}"
        upload.save()
        return f"Failed: {str(e)}"


# ─── Periodic / Cron Tasks ────────────────────────────────────────────────────

@shared_task
def cleanup_old_uploads():
    """
    Delete uploaded files older than 30 days from disk.
    Runs daily at 2 AM via Celery Beat.
    """
    from .models import DataUpload

    cutoff = datetime.now() - timedelta(days=30)
    old_uploads = DataUpload.objects.filter(uploaded_at__lt=cutoff)

    deleted_files = 0
    for upload in old_uploads:
        if upload.file and os.path.exists(upload.file.path):
            os.remove(upload.file.path)
            deleted_files += 1

    # Remove DB records too
    count = old_uploads.count()
    old_uploads.delete()

    return f"Cleaned up {deleted_files} files, {count} records older than 30 days."


@shared_task
def mark_stale_uploads():
    """
    Mark uploads stuck in 'processing' for >10 minutes as failed.
    Runs every 10 minutes via Celery Beat.
    """
    from .models import DataUpload
    from django.utils import timezone

    cutoff = timezone.now() - timedelta(minutes=10)
    stale = DataUpload.objects.filter(
        status=DataUpload.STATUS_PROCESSING,
        uploaded_at__lt=cutoff,
    )

    count = stale.update(
        status=DataUpload.STATUS_FAILED,
        error_message="Task timed out — marked as failed by stale upload monitor.",
    )

    return f"Marked {count} stale uploads as failed."


@shared_task
def refresh_forecast_cache():
    """
    Pre-compute forecast charts for all active sessions.
    Runs every 6 hours via Celery Beat.
    """
    from .models import AnalysisSession
    from .forecasting import ForecastingService

    sessions = AnalysisSession.objects.all()
    refreshed = 0

    for session in sessions:
        try:
            chart_html = ForecastingService.generate_forecast(session=session)
            if chart_html:
                cache_key = f"forecast_chart_{session.id}"
                cache.set(cache_key, chart_html, timeout=3600 * 7)  # 7 hours (overlap)
                refreshed += 1
        except Exception:
            continue

    return f"Refreshed forecast cache for {refreshed}/{len(sessions)} sessions."


@shared_task
def cleanup_old_sessions():
    """
    Delete analysis sessions with no sales data that are older than 90 days.
    Runs weekly on Sunday at 3 AM via Celery Beat.
    """
    from .models import AnalysisSession

    cutoff = datetime.now() - timedelta(days=90)
    empty_old = AnalysisSession.objects.filter(
        created_at__lt=cutoff,
        sales__isnull=True,  # no sales linked
    ).distinct()

    count = empty_old.count()
    empty_old.delete()

    return f"Deleted {count} empty sessions older than 90 days."

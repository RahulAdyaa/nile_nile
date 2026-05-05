from django.urls import path
from . import views

urlpatterns = [
    # ─── Public Pages ─────────────────────────────────────────────────────────
    path('', views.homepage, name='homepage'),
    path('about/', views.about, name='about'),

    # ─── Browser Routes (login_required) ─────────────────────────────────────
    path('dashboard/', views.dashboard_home, name='dashboard_home'),
    path('dashboard/export/<str:format>/', views.export_report, name='export_report'),
    path('dashboard/graphs/', views.graphs_page, name='graphs'),
    path('dashboard/forecasting/', views.forecasting_page, name='forecasting_page'),
    path('dashboard/anomalies/', views.anomaly_page, name='anomaly_page'),
    path('dashboard/cohorts/', views.cohort_page, name='cohort_page'),
    path('dashboard/clv/', views.clv_page, name='clv_page'),
    path('dashboard/associations/', views.associations_page, name='associations_page'),
    path('dashboard/whatif/', views.whatif_page, name='whatif_page'),
    path('dashboard/whatif/simulate/', views.whatif_simulate, name='whatif_simulate'),
    path('dashboard/report/', views.report_page, name='report_page'),
    path('dashboard/history/', views.upload_history, name='upload_history'),
    path('dashboard/tasks/', views.task_monitor, name='task_monitor'),
    path('dashboard/profile/', views.profile, name='profile'),
    path('control/', views.control_center, name='control_center'),
    path('control/upload/', views.upload_data, name='upload_data'),
    path('control/process-server-file/', views.process_server_file, name='process_server_file'),
    path('control/upload/<int:upload_id>/review/', views.review_mapping, name='review_mapping'),
    path('audit/', views.audit_log_view, name='audit_log'),
    path('flag/<int:sale_id>/', views.flag_sale, name='flag_sale'),

    # ─── Session Management ───────────────────────────────────────────────────
    path('sessions/', views.session_list, name='session_list'),
    path('sessions/new/', views.new_session, name='new_session'),
    path('sessions/<int:session_id>/restore/', views.restore_session, name='restore_session'),
    path('sessions/<int:session_id>/delete/', views.delete_session, name='delete_session'),
    path('sessions/<int:session_id>/rename/', views.rename_session, name='rename_session'),

    # ─── JWT-Protected API Routes ─────────────────────────────────────────────
    path('api/dashboard/stats/', views.api_dashboard_stats, name='api_dashboard_stats'),
    path('api/dashboard/etl/trigger/', views.api_trigger_etl, name='api_trigger_etl'),
]

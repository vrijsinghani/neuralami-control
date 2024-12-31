from django.urls import path
from . import views

app_name = 'seo_audit'

urlpatterns = [
    path('', views.AuditView.as_view(), name='audit'),
    path('start/', views.StartAuditView.as_view(), name='start_audit'),
    path('status/<int:audit_id>/', views.GetAuditStatusView.as_view(), name='audit_status'),
    path('results/<int:audit_id>/', views.GetAuditResultsView.as_view(), name='audit_results'),
    path('cancel/<int:audit_id>/', views.CancelAuditView.as_view(), name='cancel_audit'),
    path('export/<int:audit_id>/', views.ExportAuditView.as_view(), name='export_audit'),
    path('history/', views.AuditHistoryView.as_view(), name='audit_history'),
    path('get_client_website/<int:client_id>/', views.GetClientWebsiteView.as_view(), name='get_client_website'),
] 
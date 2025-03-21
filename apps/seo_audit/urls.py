from django.urls import path
from django.views.decorators.csrf import csrf_protect
from . import views

app_name = 'seo_audit'

urlpatterns = [
    path('', views.AuditView.as_view(), name='audit'),
    path('start/', views.StartAuditView.as_view(), name='start_audit'),
    path('results/<int:audit_id>/', views.GetAuditResultsView.as_view(), name='audit_results'),
    path('history/', views.AuditHistoryView.as_view(), name='audit_history'),
    path('export/<int:audit_id>/', views.ExportAuditView.as_view(), name='export_audit'),
    path('cancel/<int:audit_id>/', views.CancelAuditView.as_view(), name='cancel_audit'),
    path('status/<int:audit_id>/', views.GetAuditStatusView.as_view(), name='audit_status'),
    path('client/<int:client_id>/website/', views.GetClientWebsiteView.as_view(), name='get_client_website'),
    path('api/remediation-plan/generate/', csrf_protect(views.generate_remediation_plan), name='generate_remediation_plan'),
    path('api/remediation-plan/<int:plan_id>/', views.get_remediation_plan, name='get_remediation_plan'),  # GET request
    path('api/remediation-plan/<int:plan_id>/delete/', csrf_protect(views.delete_remediation_plan), name='delete_remediation_plan'),  # DELETE request
]
from django.contrib import admin
from .models import SEOAuditResult, SEOAuditIssue

@admin.register(SEOAuditResult)
class SEOAuditResultAdmin(admin.ModelAdmin):
    list_display = ('client', 'website', 'status', 'start_time', 'end_time', 'duration')
    list_filter = ('status', 'client', 'start_time')
    search_fields = ('website', 'client__name')
    readonly_fields = ('start_time', 'end_time', 'duration', 'task_id')
    
    def has_add_permission(self, request):
        return False  # Audits should only be created through the interface

@admin.register(SEOAuditIssue)
class SEOAuditIssueAdmin(admin.ModelAdmin):
    list_display = ('issue_type', 'severity', 'url', 'audit', 'discovered_at')
    list_filter = ('issue_type', 'severity', 'audit__client')
    search_fields = ('url', 'audit__website')
    readonly_fields = ('discovered_at',) 
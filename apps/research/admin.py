from django.contrib import admin
from django.utils.html import format_html
from .models import Research

@admin.register(Research)
class ResearchAdmin(admin.ModelAdmin):
    list_display = ['id', 'truncated_query', 'user', 'status', 'created_at', 'source_count', 'has_report']
    list_filter = ['status', 'created_at', 'user']
    search_fields = ['query', 'user__username', 'report']
    readonly_fields = ['created_at', 'updated_at', 'visited_urls', 'learnings', 'reasoning_steps']
    date_hierarchy = 'created_at'
    
    def truncated_query(self, obj):
        return obj.query[:50] + "..." if len(obj.query) > 50 else obj.query
    truncated_query.short_description = 'Query'
    
    def source_count(self, obj):
        return len(obj.visited_urls)
    source_count.short_description = 'Sources'
    
    def has_report(self, obj):
        return format_html(
            '<span style="color: {};">&#x2022;</span> {}',
            '#2ecc71' if obj.report else '#e74c3c',
            'Yes' if obj.report else 'No'
        )
    has_report.short_description = 'Report'
    
    fieldsets = [
        ('Basic Information', {
            'fields': ['user', 'query', 'status', 'created_at', 'updated_at']
        }),
        ('Research Parameters', {
            'fields': ['breadth', 'depth', 'guidance']
        }),
        ('Results', {
            'fields': ['report', 'error']
        }),
        ('Research Data', {
            'classes': ['collapse'],
            'fields': ['visited_urls', 'learnings', 'reasoning_steps']
        }),
    ] 
from django.contrib import admin
from .models import SummarizerUsage


@admin.register(SummarizerUsage)
class SummarizerUsageAdmin(admin.ModelAdmin):
    list_display = ('user', 'query', 'created_at', 'model_used')
    list_filter = ('model_used', 'created_at')
    search_fields = ('query', 'response')
    date_hierarchy = 'created_at' 
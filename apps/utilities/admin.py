from django.contrib import admin
from .models import APIEndpoint

@admin.register(APIEndpoint)
class APIEndpointAdmin(admin.ModelAdmin):
    list_display = ('name', 'method', 'url', 'created_by', 'created_at')
    list_filter = ('method', 'created_by')
    search_fields = ('name', 'url')
    readonly_fields = ('created_at', 'updated_at')
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

from django.contrib import admin
from .models import OptimizedImage

@admin.register(OptimizedImage)
class OptimizedImageAdmin(admin.ModelAdmin):
    list_display = ('original_file', 'user', 'original_size', 'optimized_size', 'compression_ratio', 'status', 'created_at')
    list_filter = ('status', 'created_at', 'user')
    search_fields = ('original_file', 'user__username')
    readonly_fields = ('compression_ratio', 'created_at')
    ordering = ('-created_at',)
    
    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing object
            return self.readonly_fields + ('original_size', 'optimized_size', 'original_file', 'optimized_file')
        return self.readonly_fields

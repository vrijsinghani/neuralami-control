from django.contrib import admin
from .models import FileInfo, FileTag

# Register your models here.


@admin.register(FileInfo)
class FileInfoAdmin(admin.ModelAdmin):
    list_display = ('filename', 'user', 'file_type', 'file_size', 'created_at', 'is_favorite')
    list_filter = ('file_type', 'is_favorite', 'created_at', 'user')
    search_fields = ('filename', 'info', 'path')
    date_hierarchy = 'created_at'


@admin.register(FileTag)
class FileTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'color')
    search_fields = ('name',)

from django.urls import path
from . import views

urlpatterns = [
    path('file-manager/', views.file_manager, name='file_manager'),
    path('file-manager/<path:directory>/', views.file_manager, name='file_manager'),
    path('download-file/<path:file_path>', views.download_file, name='download_file'),
    path('delete-file/<path:file_path>', views.delete_file, name='delete_file'),
    path('save-info/<path:file_path>', views.save_info, name='save_info'),
    path('upload-file/', views.upload_file, name='upload_file'),
]

from django.urls import path
from . import views

app_name = 'file_manager'

urlpatterns = [
    path('', views.file_manager, name='index'),  # Root view
    path('api/upload/', views.upload_file, name='upload'),  # Change upload URL
    path('download/<path:file_path>', views.download_file, name='download'),
    path('delete/<path:file_path>', views.delete_file, name='delete'),
    path('preview/<path:file_path>', views.file_preview, name='preview'),
    path('save-info/<path:file_path>/', views.save_info, name='save_info'),
    path('<path:path>/', views.file_manager, name='browse'),  # Keep this last
]

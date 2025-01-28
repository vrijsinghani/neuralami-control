from django.urls import path
from . import views

app_name = 'file_manager'

urlpatterns = [
    # Simplified URL patterns
    path('', views.file_manager, name='index'),  # Root view
    path('<path:path>/', views.file_manager, name='browse'),  # Browse directories/files
    path('delete/<path:file_path>', views.delete_file, name='delete'),
    path('api/download/<path:path>/', views.download_file, name='download'),
    path('api/upload/', views.upload_file, name='upload'),
    path('api/save-info/<path:path>/', views.save_info, name='save_info'),
]

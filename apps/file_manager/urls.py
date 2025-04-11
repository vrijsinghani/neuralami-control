from django.urls import path, re_path
from apps.file_manager import views


app_name = 'file_manager'

urlpatterns = [
    # Main file manager view
    re_path(r'^(?:/(?P<directory>.*?)/?)?$', views.file_manager, name='file_manager'),
    path('', views.file_manager, name='index'),

    # File operations
    path('delete-file/<str:file_path>/', views.delete_file, name='delete_file'),
    path('delete-file/', views.delete_file, name='delete_file'),  # For single file deletion without path
    path('delete-files/', views.delete_files, name='delete_files'),  # For batch deletion
    path('download-file/<str:file_path>/', views.download_file, name='download_file'),
    path('download-files/', views.download_file, name='download_files'),  # For batch download
    path('upload-file/', views.upload_file, name='upload_file'),
    path('save-info/<str:file_path>/', views.save_info, name='save_info'),
    path('save-info/', views.save_info, name='save_info_no_path'),  # For form submission
    path('rename-file/', views.rename_file, name='rename_file'),
    path('move-files/', views.move_files, name='move_files'),

    # Folder operations
    path('create-folder/', views.create_folder, name='create_folder'),
    path('rename-folder/', views.rename_folder, name='rename_folder'),
    path('delete-folder/', views.delete_folder, name='delete_folder'),

    # Tag operations
    path('get-file-tags/', views.get_file_tags, name='get_file_tags'),

    # File info operations
    path('get-file-info/', views.get_file_info, name='get_file_info'),
]

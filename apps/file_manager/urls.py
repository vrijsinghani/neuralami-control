from django.urls import path, re_path
from apps.file_manager import views

urlpatterns = [
    re_path(r'^file-manager(?:/(?P<directory>.*?)/?)?$', views.file_manager, name='file_manager'),
    re_path(r'^delete-file/(?P<file_path>.+)/$', views.delete_file, name='delete_file'),
    re_path(r'^download-file/(?P<file_path>.+)/$', views.download_file, name='download_file'),
    path('upload-file/', views.upload_file, name='upload_file'),
    re_path(r'^save-info/(?P<file_path>.+)/$', views.save_info, name='save_info'),
]

from django.urls import path
from . import views

app_name = 'crawl_website'

urlpatterns = [
    path('', views.index, name='index'),
    path('initiate_crawl/', views.initiate_crawl, name='initiate_crawl'),
    path('get_crawl_progress/', views.get_crawl_progress, name='get_crawl_progress'),
    path('get_crawl_result/<str:task_id>/', views.get_crawl_result, name='get_crawl_result'),
    path('get_screenshot/', views.get_screenshot, name='get_screenshot'),
]
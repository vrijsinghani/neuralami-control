from django.urls import path
from . import views

app_name = 'crawl_website'

urlpatterns = [
    path('', views.index, name='index'),
    path('crawl/', views.crawl, name='crawl'),
    path('initiate_crawl/', views.initiate_crawl, name='initiate_crawl'),
    path('get_crawl_progress/', views.get_crawl_progress, name='get_crawl_progress'),
    path('get_crawl_result/<str:task_id>/', views.get_crawl_result, name='get_crawl_result'),
    path('get_screenshot/', views.get_screenshot, name='get_screenshot'),
    path('cancel_crawl/<str:task_id>/', views.cancel_crawl, name='cancel_crawl'),
    path('active_crawls/', views.list_active_crawls, name='list_active_crawls'),
]
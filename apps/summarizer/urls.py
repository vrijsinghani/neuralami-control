from django.urls import path
from . import views

app_name = 'summarizer'

urlpatterns = [
    path('', views.summarize_view, name='summarize_view'),
    path('task_status/<str:task_id>/', views.task_status, name='task_status'),
] 
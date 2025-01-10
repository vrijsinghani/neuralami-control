from django.urls import path
from . import views

app_name = 'image_optimizer'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('optimize/', views.optimize, name='optimize'),
    path('upload/', views.handle_upload, name='handle_upload'),
    path('history/', views.optimization_history, name='history'),
] 
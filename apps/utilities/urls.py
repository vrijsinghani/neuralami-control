from django.urls import path
from . import views

app_name = 'utilities'

urlpatterns = [
    path('test-endpoint/', views.test_endpoint, name='test_endpoint'),
] 
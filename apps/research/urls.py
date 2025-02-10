from django.urls import path
from . import views

app_name = 'research'

urlpatterns = [
    path('', views.research_list, name='list'),
    path('create/', views.research_create, name='create'),
    path('<int:research_id>/', views.research_detail, name='detail'),
    path('<int:research_id>/cancel/', views.cancel_research, name='cancel'),
] 
from django.urls import path
from . import views

app_name = 'common'

urlpatterns = [
    path('api/llm/models/', views.get_llm_models, name='llm-models'),
] 
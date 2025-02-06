from django.urls import path, include
from django.views.generic import TemplateView

app_name = 'worksphere'

# API URL patterns
api_v1_patterns = [
    # Will be populated with API endpoints
]

urlpatterns = [
    # API endpoints
    path('api/v1/', include((api_v1_patterns, 'api_v1'))),
    
    # Main application entry point
    path('', TemplateView.as_view(template_name='worksphere/index.html'), name='index'),
]

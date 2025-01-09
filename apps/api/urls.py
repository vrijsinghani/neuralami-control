from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token
from apps.api.views import *

urlpatterns = [
    # Token generation endpoint
    path('token/', obtain_auth_token, name='api_token_auth'),
    
    # Tool endpoints
    path('tools/google-analytics/', GoogleAnalyticsToolView.as_view(), name='google-analytics-tool'),
    path('tools/image-optimize/', ImageOptimizeView.as_view(), name='image-optimize'),
]

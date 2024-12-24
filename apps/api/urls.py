from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token
from apps.api.views import *

urlpatterns = [
    # Token generation endpoint
    path('token/', obtain_auth_token, name='api_token_auth'),
    
    # Existing endpoints
    path('sales/', SalesView.as_view(), name='sales'),
    path('sales/<int:pk>/', SalesView.as_view(), name='sales-detail'),
    
    # Tool endpoints
    path('tools/google-analytics/', GoogleAnalyticsToolView.as_view(), name='google-analytics-tool'),
]

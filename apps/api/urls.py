from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from apps.api.views import *

router = DefaultRouter()
router.register(r'agents', AgentViewSet)
router.register(r'tasks', TaskViewSet)
router.register(r'tools', ToolViewSet)
router.register(r'crews', CrewViewSet)

urlpatterns = [
    # Existing endpoints
    path('token/', obtain_auth_token, name='api_token_auth'),
    path('tools/google-analytics/', GoogleAnalyticsToolView.as_view(), name='google-analytics-tool'),
    path('tools/image-optimize/', ImageOptimizeView.as_view(), name='image-optimize'),

    # New API endpoints
    path('', include(router.urls)),
]
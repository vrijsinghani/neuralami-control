from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/image-optimizer/(?P<optimization_id>\d+)/$', consumers.OptimizationConsumer.as_asgi()),
] 
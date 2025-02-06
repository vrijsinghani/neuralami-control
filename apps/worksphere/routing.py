from django.urls import re_path
from channels.routing import URLRouter
from channels.auth import AuthMiddlewareStack

# Import consumers as they are created
# from .websockets.chat import ChatConsumer

websocket_urlpatterns = [
    # Will be populated with WebSocket consumers
    # re_path(r'ws/chat/$', ChatConsumer.as_asgi()),
]

# Apply authentication middleware to all WebSocket routes
websocket_router = AuthMiddlewareStack(
    URLRouter(websocket_urlpatterns)
)

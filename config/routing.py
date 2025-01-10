from django.urls import path, re_path
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

from apps.image_optimizer.routing import websocket_urlpatterns as image_optimizer_websocket_urlpatterns

application = ProtocolTypeRouter({
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                image_optimizer_websocket_urlpatterns
            )
        )
    ),
}) 
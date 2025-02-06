import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from apps.agents.routing import websocket_urlpatterns as agent_websocket_urlpatterns
from apps.worksphere.routing import websocket_urlpatterns as worksphere_websocket_urlpatterns

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            agent_websocket_urlpatterns +
            worksphere_websocket_urlpatterns
        )
    ),
})

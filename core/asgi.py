import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from core.routing import websocket_urlpatterns
from apps.organizations.middleware import OrganizationMiddlewareAsync

# Apply standard middleware chaining for WebSockets:
# 1. Auth middleware for authentication
# 2. Organization middleware for setting organization context
# 3. URL router for routing to appropriate consumer

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        OrganizationMiddlewareAsync(
            URLRouter(
                websocket_urlpatterns
            )
        )
    ),
})

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import re_path
from apps.agents.kanban_consumers import CrewKanbanConsumer
from apps.agents.consumers import ConnectionTestConsumer, CrewExecutionConsumer
from apps.agents.websockets import ChatConsumer
from apps.seo_audit.consumers import SEOAuditConsumer

websocket_urlpatterns = [
    re_path(r'ws/connection_test/$', ConnectionTestConsumer.as_asgi()),
    re_path(r'ws/crew_execution/(?P<execution_id>\w+)/$', CrewExecutionConsumer.as_asgi()),
    re_path(r'ws/chat/(?P<session>[^/]+)?/?$', ChatConsumer.as_asgi()),
    re_path(r'ws/crew/(?P<crew_id>\w+)/kanban/$', CrewKanbanConsumer.as_asgi()),
    re_path(r'ws/seo_audit/(?P<audit_id>\d+)/$', SEOAuditConsumer.as_asgi()),
]

application = ProtocolTypeRouter({
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
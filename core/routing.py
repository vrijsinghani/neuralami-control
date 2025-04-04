from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import re_path
from apps.agents.kanban_consumers import CrewKanbanConsumer
from apps.agents.consumers import ConnectionTestConsumer, CrewExecutionConsumer
from apps.agents.websockets import ChatConsumer
from apps.seo_audit.consumers import SEOAuditConsumer
from apps.image_optimizer.consumers import OptimizationConsumer
from apps.research.websockets.research_consumer import ResearchConsumer
from apps.seo_manager.consumers import MetaTagsTaskConsumer
# Import crawl website routes
from apps.crawl_website.routing import websocket_urlpatterns as crawl_websocket_urlpatterns

websocket_urlpatterns = [
    re_path(r'ws/connection_test/$', ConnectionTestConsumer.as_asgi()),
    re_path(r'ws/crew_execution/(?P<execution_id>\w+)/$', CrewExecutionConsumer.as_asgi()),
    re_path(r'ws/chat/(?P<session>[^/]+)?/?$', ChatConsumer.as_asgi()),
    re_path(r'ws/crew/(?P<crew_id>\w+)/kanban/$', CrewKanbanConsumer.as_asgi()),
    re_path(r'ws/seo_audit/(?P<audit_id>\d+)/$', SEOAuditConsumer.as_asgi()),
    re_path(r'ws/image-optimizer/(?P<optimization_id>\d+)/$', OptimizationConsumer.as_asgi()),
    re_path(r'ws/research/(?P<research_id>\d+)/$', ResearchConsumer.as_asgi()),
    re_path(r'ws/meta-tags/task/(?P<task_id>[\w-]+)/$', MetaTagsTaskConsumer.as_asgi()),
]

# Append crawl website routes
websocket_urlpatterns += crawl_websocket_urlpatterns

application = ProtocolTypeRouter({
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
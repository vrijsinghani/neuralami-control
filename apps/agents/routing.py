from django.urls import re_path
from .consumers import ConnectionTestConsumer, ChatConsumer, CrewExecutionConsumer
from .kanban_consumers import CrewKanbanConsumer

websocket_urlpatterns = [
    re_path(r'ws/chat/$', ChatConsumer.as_asgi()),
    re_path(r'ws/crew_execution/(?P<execution_id>\w+)/$', CrewExecutionConsumer.as_asgi()),
    re_path(r'ws/test-connection/$', ConnectionTestConsumer.as_asgi()),
]
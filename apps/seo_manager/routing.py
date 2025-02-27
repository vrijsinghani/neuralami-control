from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/meta-tags/task/(?P<task_id>[\w-]+)/$', consumers.MetaTagsTaskConsumer.as_asgi()),
] 
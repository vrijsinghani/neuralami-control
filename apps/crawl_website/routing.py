from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/crawl/(?P<task_id>[\w-]+)/$', consumers.CrawlConsumer.as_asgi()),
] 
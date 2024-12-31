from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/seo_audit/(?P<audit_id>\d+)/$', consumers.SEOAuditConsumer.as_asgi()),
] 
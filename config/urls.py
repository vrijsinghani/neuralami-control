from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # ... your other URL patterns ...
]

# Add static files handling for development only
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) 
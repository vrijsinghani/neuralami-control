"""
URL configuration for core project.
"""
import logging
import mimetypes
logger = logging.getLogger(__name__)
logger.info("==== CORE URLS LOADED ====")

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from django.http import HttpResponse, Http404, FileResponse
from home import views
from django.views.static import serve
from apps.seo_manager import views as seo_views
import logging
from core.views import serve_protected_file

logger = logging.getLogger(__name__)

logger.info("Starting admin module imports")

# Import admin modules to ensure they are registered
try:
    from apps.agents import admin as agents_admin
    logger.info("Successfully imported agents admin")
except Exception as e:
    logger.error(f"Failed to import agents admin: {str(e)}")

try:
    from apps.seo_manager import admin as seo_manager_admin
    logger.info("Successfully imported seo_manager admin")
except Exception as e:
    logger.error(f"Failed to import seo_manager admin: {str(e)}")

try:
    from apps.seo_audit import admin as seo_audit_admin
    logger.info("Successfully imported seo_audit admin")
except Exception as e:
    logger.error(f"Failed to import seo_audit admin: {str(e)}")

try:
    from apps.common import admin as common_admin
    logger.info("Successfully imported common admin")
except Exception as e:
    logger.error(f"Failed to import common admin: {str(e)}")

#logger.info(f"Admin site registry after imports: {list(admin.site._registry.keys())}")

handler404 = 'home.views.error_404'
handler500 = 'home.views.error_500'

# Configure admin site
admin.site.site_header = 'NeuralAMI Control'
admin.site.site_title = 'NeuralAMI Control'
admin.site.index_title = 'Administration'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('home.urls')),
    path("api/", include("apps.api.urls")),
    path('tasks/', include('apps.tasks.urls')),
    path('file-manager/', include('apps.file_manager.urls')),
    path("users/", include("apps.users.urls")),
    path('accounts/', include('allauth.urls')),
    path('', include('apps.common.urls', namespace='common')),

    # Serve media files from cloud storage
    re_path(r'^static/(?P<path>.*)$', serve,{'document_root': settings.STATIC_ROOT}), 
    
    # Serve protected storage files with authentication/authorization
    path('media/secure/<path:path>', serve_protected_file, name='serve_protected_file'),

    path('crawl_website/', include('apps.crawl_website.urls')),

    path("__debug__/", include("debug_toolbar.urls")),
    
    # Add Google OAuth callback at root level
    path('google/login/callback/', seo_views.analytics_views.google_oauth_callback, name='root_google_oauth_callback'),
]

urlpatterns += [
    path('seo/', include('apps.seo_manager.urls', namespace='seo_manager')),
    path('agents/', include('apps.agents.urls', namespace='agents')),
    path('seo-audit/', include('apps.seo_audit.urls', namespace='seo_audit')),
    path('image-optimizer/', include('apps.image_optimizer.urls', namespace='image_optimizer')),
    path('research/', include('apps.research.urls', namespace='research')),
    path('utilities/', include('apps.utilities.urls', namespace='utilities')),
    path('organization/', include('apps.organizations.urls', namespace='organizations')),
]

from django.http import HttpResponse

def health_check(request):
    return HttpResponse("OK")

urlpatterns += [
    path('health/', health_check, name='health_check'),
]
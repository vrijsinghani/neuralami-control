"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from home import views
from django.views.static import serve
from apps.seo_manager import views as seo_views

handler404 = 'home.views.error_404'
handler500 = 'home.views.error_500'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('home.urls')),
    path("api/", include("apps.api.urls")),
    path('charts/', include('apps.charts.urls')),
    path('tasks/', include('apps.tasks.urls')),
    path("tables/", include("apps.tables.urls")),
    path('', include('apps.file_manager.urls')),
    path("users/", include("apps.users.urls")),
    path('accounts/', include('allauth.urls')),

    re_path(r'^media/(?P<path>.*)$', serve,{'document_root': settings.MEDIA_ROOT}), 
    re_path(r'^static/(?P<path>.*)$', serve,{'document_root': settings.STATIC_ROOT}), 

    path('crawl_website/', include('apps.crawl_website.urls')),

    path("__debug__/", include("debug_toolbar.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

urlpatterns += [
    path('seo/', include('apps.seo_manager.urls', namespace='seo_manager')),
    path('agents/', include('apps.agents.urls', namespace='agents')),
    path('google/login/callback/', seo_views.google_oauth_callback, name='google_oauth_callback'),
]
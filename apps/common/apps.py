from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class CommonConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.common'
    verbose_name = 'Common'

    def ready(self):
        """Initialize app when Django starts."""
        logger.info("Common app ready() called")
        
        # Log admin site state
        from django.contrib import admin
        logger.info(f"Admin site registry: {list(admin.site._registry.keys())}")
        
        # Log all installed apps
        from django.apps import apps
        logger.info(f"All installed apps: {[app.name for app in apps.get_app_configs()]}")
        
        # Log database configuration
        from django.conf import settings
        logger.info(f"Database config: {settings.DATABASES}")
        
        # Log middleware
        logger.info(f"Middleware: {settings.MIDDLEWARE}")

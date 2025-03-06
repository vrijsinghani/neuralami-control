from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class OrganizationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.organizations'
    
    def ready(self):
        """
        Apply organization security enhancements when the app is ready.
        This includes patching Django's shortcuts with our secure versions.
        """
        logger.info("Initializing organization security features")
        
        # Patch Django's shortcuts with secure versions
        from .shortcuts import patch_django_shortcuts
        patch_django_shortcuts()
        
        logger.info("Organization security features initialized")

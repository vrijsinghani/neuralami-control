from django.apps import AppConfig


class WorksphereConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.worksphere'
    label = 'worksphere'
    verbose_name = 'WorkSphere'

    def ready(self):
        """
        Initialize app-specific configurations and signal handlers
        """
        try:
            # Import signal handlers
            import apps.worksphere.signals  # noqa
        except ImportError:
            pass

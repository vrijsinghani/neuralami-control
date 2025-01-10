from django.apps import AppConfig


class ImageOptimizerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.image_optimizer'
    verbose_name = 'Image Optimizer'

    def ready(self):
        try:
            import apps.image_optimizer.signals
        except ImportError:
            pass

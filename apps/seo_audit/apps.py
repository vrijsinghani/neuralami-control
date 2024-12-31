from django.apps import AppConfig
import os

class SEOAuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.seo_audit'
    verbose_name = 'SEO Audit'
    path = os.path.dirname(os.path.abspath(__file__))

    def ready(self):
        try:
            import apps.seo_audit.signals  # noqa
        except ImportError:
            pass 
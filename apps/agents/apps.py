from django.apps import AppConfig


class AgentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.agents'
    verbose_name = 'CrewAI Agents'

    def ready(self):
        pass  # We'll add any necessary imports or setup here later if needed

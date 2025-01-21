from django.core.management.base import BaseCommand
from django.db import connections
from apps.seo_manager.models import (
    Client, ClientGroup, GoogleAnalyticsCredentials,
    SearchConsoleCredentials, TargetedKeyword, SEOData, SEOProject
)
from apps.agents.models import (
    Tool, Agent, Task, Crew, CrewTask, AgentToolSettings,
    Pipeline, PipelineStage, PipelineRoute
)

class Command(BaseCommand):
    help = 'Copy Client and Agent data from source database to target database'

    def add_arguments(self, parser):
        parser.add_argument('--source', type=str, default='default', help='Source database')
        parser.add_argument('--target', type=str, required=True, help='Target database')

    def handle(self, *args, **options):
        source_db = options['source']
        target_db = options['target']

        # Validate databases exist
        if source_db not in connections or target_db not in connections:
            self.stderr.write(self.style.ERROR(f"Database configuration missing for {source_db} or {target_db}"))
            return

        # Models to copy in order (parent models first)
        # Client-related models
        client_models = [
            ClientGroup,
            Client,
            GoogleAnalyticsCredentials,
            SearchConsoleCredentials,
            TargetedKeyword,
            SEOData,
            SEOProject
        ]

        # Agent-related models (excluding log/execution tables)
        agent_models = [
            Tool,
            Agent,
            Task,
            Crew,
            CrewTask,
            AgentToolSettings,
            Pipeline,
            PipelineStage,
            PipelineRoute
        ]

        # Copy client-related models
        self.stdout.write(self.style.NOTICE("Copying client-related models..."))
        for model in client_models:
            self.copy_model(model, source_db, target_db)

        # Copy agent-related models
        self.stdout.write(self.style.NOTICE("Copying agent-related models..."))
        for model in agent_models:
            self.copy_model(model, source_db, target_db)

        self.stdout.write(self.style.SUCCESS('Successfully copied all data'))

    def copy_model(self, model, source_db, target_db):
        self.stdout.write(f"Copying {model.__name__}...")
        
        try:
            # Get all objects from source
            objects = list(model.objects.using(source_db).all())
            
            if not objects:
                self.stdout.write(self.style.NOTICE(f"No {model.__name__} objects to copy"))
                return

            # Reset PKs and save to target
            for obj in objects:
                # Store original pk
                original_pk = obj.pk
                # Reset the primary key
                obj.pk = None
                # Save to target database
                try:
                    obj.save(using=target_db)
                    self.stdout.write(f"Copied {model.__name__} {original_pk} -> {obj.pk}")
                except Exception as e:
                    self.stderr.write(self.style.ERROR(
                        f"Error copying {model.__name__} {original_pk}: {str(e)}"
                    ))

            self.stdout.write(self.style.SUCCESS(
                f"Copied {len(objects)} {model.__name__} objects"
            ))
            
        except Exception as e:
            self.stderr.write(self.style.ERROR(
                f"Error processing {model.__name__}: {str(e)}"
            ))
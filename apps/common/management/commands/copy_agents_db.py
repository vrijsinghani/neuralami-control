from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from apps.agents import models as agent_models
from django.db.models import Max

class Command(BaseCommand):
    help = 'Copy data from agents app models (excluding runtime results) from source database to target database'

    def add_arguments(self, parser):
        parser.add_argument('--source', type=str, default='default', help='Source database')
        parser.add_argument('--target', type=str, required=True, help='Target database')
        parser.add_argument('--skip-migrations', action='store_true', help='Skip running migrations on target database')

    def handle(self, *args, **options):
        source_db = options['source']
        target_db = options['target']
        skip_migrations = options['skip_migrations']

        # Check databases
        if source_db not in connections:
            self.stderr.write(self.style.ERROR(f"Source database '{source_db}' is not configured"))
            return
        if target_db not in connections:
            self.stderr.write(self.style.ERROR(f"Target database '{target_db}' is not configured"))
            return

        # Run migrations if needed
        if not skip_migrations:
            executor = MigrationExecutor(connections[target_db])
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            if plan:
                self.stdout.write(self.style.NOTICE('Target database needs migrations. Running migrations first...'))
                executor.migrate(targets=executor.loader.graph.leaf_nodes(), plan=plan)

        # Models to exclude (runtime results)
        excluded_models = {'CrewExecution', 'CrewMessage', 'CrewOutput', 'ChatMessage', 'TokenUsage', 'ToolRun', 'Conversation', 'CrewChatSession'}

        # Get only models from agents app, excluding runtime results
        all_models = [
            m for m in apps.get_models() 
            if m.__module__ == 'apps.agents.models' 
            and m.__name__ not in excluded_models
        ]
        m2m_data = {}  # Store all M2M relationships

        # First pass: Copy all models without M2M relationships
        for model in all_models:
            try:
                self.stdout.write(f"Copying {model.__name__}...")
                
                # Get all objects from source
                objects = list(model.objects.using(source_db).all())
                
                if not objects:
                    self.stdout.write(self.style.NOTICE(f"No {model.__name__} objects to copy"))
                    continue

                # Store M2M relationships
                m2m_data[model] = {}
                for obj in objects:
                    m2m_fields = [f for f in obj._meta.get_fields() if f.many_to_many and not f.auto_created]
                    if m2m_fields:
                        m2m_data[model][obj.pk] = {
                            field.name: list(getattr(obj, field.name).all().values_list('pk', flat=True))
                            for field in m2m_fields
                        }

                # Clear target
                try:
                    model.objects.using(target_db).all().delete()
                except Exception as e:
                    self.stderr.write(self.style.WARNING(f"Could not clear {model.__name__}: {str(e)}"))

                # Copy objects
                new_objects = model.objects.using(target_db).bulk_create(
                    objects,
                    batch_size=1000,
                    ignore_conflicts=True
                )

                self.stdout.write(self.style.SUCCESS(f"Copied {len(objects)} {model.__name__} objects"))

            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error copying {model.__name__}: {str(e)}"))
                continue

        # Second pass: Restore M2M relationships
        self.stdout.write(self.style.NOTICE("Restoring many-to-many relationships..."))
        
        for model, relationships in m2m_data.items():
            try:
                for obj_id, fields in relationships.items():
                    try:
                        obj = model.objects.using(target_db).get(pk=obj_id)
                        for field_name, related_ids in fields.items():
                            m2m_field = getattr(obj, field_name)
                            m2m_field.clear()
                            m2m_field.add(*related_ids)
                    except model.DoesNotExist:
                        self.stderr.write(self.style.WARNING(f"Could not find {model.__name__} with pk {obj_id}"))
                        continue
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error restoring M2M relationships for {model.__name__}: {str(e)}"))
                continue

        self.stdout.write(self.style.SUCCESS('Successfully completed agents database copy operation (excluding runtime results)'))

    def copy_model(self, model, source_using='default', target_using='target'):
        objects = model.objects.using(source_using).all()
        if not objects:
            self.stdout.write(f'No {model.__name__} objects to copy')
            return
        
        self.stdout.write(f'Copying {model.__name__}...')
        
        # Get the max ID from the target database
        max_id_target = model.objects.using(target_using).aggregate(Max('id'))['id__max'] or 0
        
        # Create a mapping of old IDs to new IDs
        id_mapping = {}
        
        for obj in objects:
            old_id = obj.id
            # Assign a new ID that's guaranteed to be unique
            obj.id = max_id_target + old_id + 1
            id_mapping[old_id] = obj.id
        
        model.objects.using(target_using).bulk_create(objects)
        self.stdout.write(f'Copied {len(objects)} {model.__name__} objects')
        
        return id_mapping

    def restore_m2m_relationships(self, model, id_mapping, source_using='default', target_using='target'):
        try:
            for obj in model.objects.using(source_using).all():
                new_obj = model.objects.using(target_using).get(id=id_mapping[obj.id])
                
                # Get all M2M fields
                for field in model._meta.many_to_many:
                    # Get the related objects from source
                    related_objects = getattr(obj, field.name).all()
                    
                    # Clear existing relationships in target
                    getattr(new_obj, field.name).clear()
                    
                    # Add the mapped related objects
                    for related_obj in related_objects:
                        if hasattr(related_obj, 'id'):
                            mapped_id = id_mapping.get(related_obj.id)
                            if mapped_id:
                                getattr(new_obj, field.name).add(mapped_id)
        
        except Exception as e:
            self.stdout.write(f'Error restoring M2M relationships for {model.__name__}: {str(e)}')
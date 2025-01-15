from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import connections, router, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models import ForeignKey, ManyToManyField
from django.db.utils import OperationalError, ProgrammingError
from collections import defaultdict
import logging
import time

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Copy data from source database to target database'

    def add_arguments(self, parser):
        parser.add_argument('--source', type=str, default='default', help='Source database')
        parser.add_argument('--target', type=str, required=True, help='Target database')
        parser.add_argument('--skip-migrations', action='store_true', help='Skip running migrations on target database')
        parser.add_argument('--batch-size', type=int, default=100, help='Batch size for copying objects')
        parser.add_argument('--max-retries', type=int, default=3, help='Maximum number of retries for failed operations')
        parser.add_argument('--retry-delay', type=int, default=1, help='Delay in seconds between retries')

    def analyze_model_dependencies(self, model):
        """Analyze model dependencies including both FK and M2M relationships"""
        dependencies = set()
        circular_deps = set()
        
        # Get all fields including those from parent models
        fields = []
        for parent in model._meta.get_parent_list():
            fields.extend(parent._meta.local_fields)
        fields.extend(model._meta.local_fields)
        fields.extend(model._meta.local_many_to_many)
        
        # Check foreign key dependencies
        for field in fields:
            if isinstance(field, (ForeignKey, ManyToManyField)):
                related_model = field.remote_field.model
                if related_model == model:  # Self-reference
                    circular_deps.add(model)
                else:
                    # Check if this creates a circular dependency through inheritance
                    if not issubclass(model, related_model) and not issubclass(related_model, model):
                        dependencies.add(related_model)
                    else:
                        circular_deps.add(model)

        return dependencies, circular_deps

    def build_dependency_graph(self, models):
        """Build a complete dependency graph with circular dependency detection"""
        graph = {}
        circular_dependencies = set()
        
        for model in models:
            deps, circular = self.analyze_model_dependencies(model)
            graph[model] = deps
            circular_dependencies.update(circular)
            
        return graph, circular_dependencies

    def sort_models(self, models):
        """Sort models based on dependencies with circular dependency handling"""
        graph, circular_deps = self.build_dependency_graph(models)
        sorted_models = []
        visiting = set()
        visited = set()

        def visit(model):
            if model in visiting:  # Circular dependency detected
                return
            if model in visited:
                return
                
            visiting.add(model)
            
            # First handle dependencies that aren't circular
            deps = graph.get(model, set())
            non_circular_deps = deps - circular_deps
            for dep in non_circular_deps:
                visit(dep)
                
            visiting.remove(model)
            visited.add(model)
            sorted_models.append(model)

        # First process models without circular dependencies
        for model in models:
            if model not in circular_deps:
                visit(model)

        # Then handle models with circular dependencies
        for model in models:
            if model not in visited:
                visit(model)

        return sorted_models

    def retry_operation(self, operation, max_retries, retry_delay, *args, **kwargs):
        """Retry an operation with exponential backoff"""
        last_error = None
        for attempt in range(max_retries):
            try:
                return operation(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt == max_retries - 1:
                    break
                delay = retry_delay * (2 ** attempt)
                self.stdout.write(self.style.WARNING(
                    f"Operation failed: {str(e)}, retrying in {delay}s... ({attempt + 1}/{max_retries})"
                ))
                time.sleep(delay)
        raise last_error

    def copy_model_objects(self, model, source_db, target_db, batch_size, max_retries, retry_delay):
        """Copy objects for a single model with error handling and retries"""
        try:
            # Check if table exists
            with connections[target_db].cursor() as cursor:
                try:
                    cursor.execute(
                        "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
                        [model._meta.db_table]
                    )
                    if not cursor.fetchone():
                        self.stdout.write(self.style.WARNING(
                            f"Skipping {model.__name__}: Table does not exist in target database"
                        ))
                        return None
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error checking table existence: {str(e)}"))
                    return None

            # Get source objects
            objects = list(model.objects.using(source_db).all())
            if not objects:
                self.stdout.write(self.style.NOTICE(f"No {model.__name__} objects to copy"))
                return None

            # Clear target
            with transaction.atomic(using=target_db):
                model.objects.using(target_db).all().delete()

            # Copy in batches with retries
            for i in range(0, len(objects), batch_size):
                batch = objects[i:i + batch_size]
                def copy_batch():
                    with transaction.atomic(using=target_db):
                        return model.objects.using(target_db).bulk_create(
                            batch,
                            batch_size=batch_size,
                            ignore_conflicts=True
                        )
                self.retry_operation(copy_batch, max_retries, retry_delay)

            self.stdout.write(self.style.SUCCESS(f"Copied {len(objects)} {model.__name__} objects"))
            return objects

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error copying {model.__name__}: {str(e)}"))
            return None

    def handle(self, *args, **options):
        source_db = options['source']
        target_db = options['target']
        skip_migrations = options['skip_migrations']
        batch_size = options['batch_size']
        max_retries = options['max_retries']
        retry_delay = options['retry_delay']

        # Validate database configurations
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

        # Get all models and sort them by dependencies
        all_models = apps.get_models()
        sorted_models = self.sort_models(all_models)
        
        # Store M2M relationships
        m2m_data = defaultdict(dict)
        
        # First pass: Copy models in dependency order
        for model in sorted_models:
            objects = self.copy_model_objects(
                model, source_db, target_db, batch_size, max_retries, retry_delay
            )
            
            if not objects:
                continue

            # Store M2M relationships
            for obj in objects:
                m2m_fields = [
                    f for f in obj._meta.get_fields()
                    if f.many_to_many and not f.auto_created
                ]
                if m2m_fields:
                    m2m_data[model][obj.pk] = {}
                    for field in m2m_fields:
                        try:
                            related_ids = list(
                                getattr(obj, field.name)
                                .all()
                                .values_list('pk', flat=True)
                            )
                            m2m_data[model][obj.pk][field.name] = related_ids
                        except Exception as e:
                            self.stderr.write(self.style.WARNING(
                                f"Error storing M2M relationship {field.name} for "
                                f"{model.__name__} {obj.pk}: {str(e)}"
                            ))

        # Second pass: Restore M2M relationships
        self.stdout.write(self.style.NOTICE("Restoring many-to-many relationships..."))
        
        for model, relationships in m2m_data.items():
            for obj_id, fields in relationships.items():
                try:
                    obj = model.objects.using(target_db).get(pk=obj_id)
                    for field_name, related_ids in fields.items():
                        m2m_field = getattr(obj, field_name)
                        m2m_field.clear()
                        
                        # Add related objects in batches with retries
                        for i in range(0, len(related_ids), batch_size):
                            batch_ids = related_ids[i:i + batch_size]
                            def add_m2m_batch():
                                with transaction.atomic(using=target_db):
                                    m2m_field.add(*batch_ids)
                            try:
                                self.retry_operation(
                                    add_m2m_batch, max_retries, retry_delay
                                )
                            except Exception as e:
                                self.stderr.write(self.style.WARNING(
                                    f"Error restoring M2M relationship {field_name} for "
                                    f"{model.__name__} {obj_id}: {str(e)}"
                                ))
                                
                except model.DoesNotExist:
                    self.stderr.write(self.style.WARNING(
                        f"Could not find {model.__name__} with pk {obj_id}"
                    ))
                except Exception as e:
                    self.stderr.write(self.style.ERROR(
                        f"Error processing M2M relationships for {model.__name__} "
                        f"{obj_id}: {str(e)}"
                    ))

        self.stdout.write(self.style.SUCCESS('Successfully completed database copy operation'))

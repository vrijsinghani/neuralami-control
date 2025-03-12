from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import connections, router, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models import ForeignKey, ManyToManyField, CASCADE, SET_NULL
from django.db.utils import OperationalError, ProgrammingError
from collections import defaultdict
import logging
import time
import inspect

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
                
                # Check for self-reference
                if related_model == model:
                    circular_deps.add(model)
                    continue
                    
                # Check if this creates a circular dependency through inheritance
                if issubclass(model, related_model) or issubclass(related_model, model):
                    circular_deps.add(model)
                    continue
                    
                # Check for potential cross-model circular dependencies
                # We'll mark these for special handling in the copy process
                if field.remote_field.on_delete == SET_NULL:
                    # Models with SET_NULL are candidates for circular dependencies
                    dependencies.add(related_model)
                    
                    # Check if the related model has a reverse relation to this model
                    for related_field in related_model._meta.fields:
                        if isinstance(related_field, ForeignKey) and related_field.remote_field.model == model:
                            # This is a potential circular dependency
                            circular_deps.add(model)
                            circular_deps.add(related_model)
                else:
                    # Regular dependency
                    dependencies.add(related_model)

        return dependencies, circular_deps

    def build_dependency_graph(self, models):
        """Build a complete dependency graph with circular dependency detection"""
        graph = {}
        circular_dependencies = set()
        cascade_dependencies = {}  # Track CASCADE dependencies separately
        
        for model in models:
            deps, circular = self.analyze_model_dependencies(model)
            graph[model] = deps
            circular_dependencies.update(circular)
            
            # Track which models have CASCADE dependencies on this model
            for other_model in models:
                if other_model == model:
                    continue
                    
                for field in other_model._meta.fields:
                    if isinstance(field, ForeignKey) and field.remote_field.model == model:
                        if field.remote_field.on_delete == CASCADE:
                            if model not in cascade_dependencies:
                                cascade_dependencies[model] = set()
                            cascade_dependencies[model].add(other_model)
        
        return graph, circular_dependencies, cascade_dependencies

    def sort_models(self, models):
        """Sort models based on dependencies with special handling for CASCADE relationships"""
        graph, circular_deps, cascade_deps = self.build_dependency_graph(models)
        sorted_models = []
        visiting = set()
        visited = set()
        
        # First, identify models that are referenced by CASCADE foreign keys
        # These need to be processed first to avoid foreign key constraint violations
        cascade_referenced_models = set(cascade_deps.keys())

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

        # First process models that are referenced by CASCADE foreign keys
        for model in models:
            if model in cascade_referenced_models and model not in visited:
                visit(model)

        # Then process models without circular dependencies
        for model in models:
            if model not in circular_deps and model not in visited:
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

    def uses_organization_mixin(self, model):
        """Check if a model inherits from OrganizationModelMixin"""
        try:
            # Try to import the mixin
            from apps.organizations.models.mixins import OrganizationModelMixin
            
            # Check if model inherits from the mixin
            return issubclass(model, OrganizationModelMixin)
        except (ImportError, TypeError):
            return False

    def get_model_manager(self, model, source_db):
        """Get the appropriate manager for the model based on whether it uses OrganizationModelMixin"""
        if self.uses_organization_mixin(model):
            self.stdout.write(self.style.NOTICE(
                f"Using unfiltered_objects manager for {model.__name__} (OrganizationModelMixin)"
            ))
            return model.unfiltered_objects.using(source_db)
        else:
            return model.objects.using(source_db)

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
                        return None, None
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error checking table existence: {str(e)}"))
                    return None, None

            # Get source objects, using the appropriate manager
            manager = self.get_model_manager(model, source_db)
            objects = list(manager.all())
            
            if not objects:
                self.stdout.write(self.style.NOTICE(f"No {model.__name__} objects to copy"))
                return None, None

            # Clear target - must use target manager
            target_manager = self.get_model_manager(model, target_db)
            with transaction.atomic(using=target_db):
                target_manager.all().delete()

            # Check for circular dependencies
            _, circular_deps, _ = self.build_dependency_graph([model])
            has_circular_deps = model in circular_deps
            
            # Store for circular dependency restoration
            circular_fk_data = {}
            
            # If this model has circular dependencies, we need to temporarily set those fields to NULL
            if has_circular_deps:
                self.stdout.write(self.style.NOTICE(
                    f"Model {model.__name__} has circular dependencies, handling specially"
                ))
                
                # Find fields that create circular dependencies
                circular_fields = []
                for field in model._meta.fields:
                    if isinstance(field, ForeignKey) and field.remote_field.model in circular_deps:
                        circular_fields.append(field.name)
                        
                # Store original values and set fields to None
                if circular_fields:
                    for obj in objects:
                        obj_id = obj.pk
                        circular_fk_data[obj_id] = {}
                        for field_name in circular_fields:
                            value = getattr(obj, field_name)
                            if value is not None:
                                circular_fk_data[obj_id][field_name] = value.pk
                            setattr(obj, field_name, None)

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
            
            # Return the circular FK data for later restoration
            if has_circular_deps and circular_fk_data:
                return objects, circular_fk_data
            return objects, None

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error copying {model.__name__}: {str(e)}"))
            return None, None

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
        
        # Identify M2M through models for special handling
        through_models = set()
        for model in all_models:
            for field in model._meta.get_fields():
                if field.many_to_many and not field.auto_created:
                    if hasattr(field, 'through') and field.through is not None and field.through != models.ManyToManyField.through:
                        # Add the through model to our set for special handling
                        through_models.add(field.through)
                        
        self.stdout.write(self.style.NOTICE(
            f"Identified {len(through_models)} M2M through models for special handling: "
            f"{', '.join(m.__name__ for m in through_models)}"
        ))
        
        sorted_models = self.sort_models(all_models)
        
        # Move through models to the end of the list to ensure their related models are processed first
        # This is important because through models often have foreign keys back to the main models
        for through_model in through_models:
            if through_model in sorted_models:
                sorted_models.remove(through_model)
                sorted_models.append(through_model)
                
        # First pass: Copy all objects
        m2m_data = {}  # Store M2M data for later restoration
        circular_deps = {}  # Store circular dependencies for later restoration
        cross_model_circular_deps = {}  # Store circular dependencies across models
        
        # Store M2M relationships
        for model in sorted_models:
            objects, circular_fk_data = self.copy_model_objects(
                model, source_db, target_db, batch_size, max_retries, retry_delay
            )
            
            if not objects:
                continue
                
            # Store circular FK data for later restoration
            if circular_fk_data:
                circular_deps[model] = circular_fk_data

            # Store M2M relationships
            for obj in objects:
                m2m_fields = [
                    f for f in obj._meta.get_fields()
                    if f.many_to_many and not f.auto_created
                ]
                if m2m_fields:
                    m2m_data[model] = m2m_data.get(model, {})
                    m2m_data[model][obj.pk] = {}
                    for field in m2m_fields:
                        try:
                            # Get the related manager
                            related_manager = getattr(obj, field.name)
                            
                            # Check if this is a M2M with a through model
                            has_through_model = hasattr(field, 'through') and field.through is not None
                            
                            # If this is an OrganizationModelMixin model, we need special handling
                            if self.uses_organization_mixin(field.related_model):
                                # Use unfiltered_objects to get all related objects
                                related_ids = list(
                                    field.related_model.unfiltered_objects.using(source_db)
                                    .filter(pk__in=related_manager.values_list('pk', flat=True))
                                    .values_list('pk', flat=True)
                                )
                            else:
                                # Normal case - use the all() method on the related manager
                                related_ids = list(
                                    related_manager
                                    .all()
                                    .values_list('pk', flat=True)
                                )
                                
                            m2m_data[model][obj.pk][field.name] = {
                                'ids': related_ids,
                                'through_model': field.through._meta.model_name if has_through_model else None
                            }
                            
                            # If this is a M2M with a through model, we need to store additional data
                            if has_through_model:
                                through_model = field.through
                                
                                # Log that we're dealing with a through model for debugging
                                self.stdout.write(self.style.NOTICE(
                                    f"Detected M2M with through model: {model.__name__}.{field.name} -> {through_model.__name__}"
                                ))
                                
                                # Get all through model instances for this relationship
                                through_objects_query = through_model.objects.using(source_db).filter(**{
                                    field.m2m_field_name(): obj.pk
                                })
                                
                                # Store each through model instance with its relation details
                                through_data = []
                                for through_obj in through_objects_query:
                                    through_data.append({
                                        'related_id': getattr(through_obj, field.m2m_reverse_field_name()),
                                        'through_data': {
                                            field_name: getattr(through_obj, field_name)
                                            for field_name in [f.name for f in through_model._meta.fields 
                                                              if f.name not in ('id', field.m2m_field_name(), field.m2m_reverse_field_name())]
                                        }
                                    })
                                
                                # Store the through model data
                                m2m_data[model][obj.pk][field.name]['through_data'] = through_data
                            
                        except Exception as e:
                            self.stderr.write(self.style.WARNING(
                                f"Error storing M2M relationship {field.name} for "
                                f"{model.__name__} {obj.pk}: {str(e)}"
                            ))
                
                # Store cross-model circular dependencies for third pass
                for field in obj._meta.fields:
                    if isinstance(field, ForeignKey):
                        related_model = field.remote_field.model
                        # Check if this is a cross-model circular dependency
                        if related_model in circular_deps and related_model != model:
                            field_value = getattr(obj, field.name + '_id', None)
                            if field_value is not None:
                                cross_model_circular_deps[model] = cross_model_circular_deps.get(model, [])
                                cross_model_circular_deps[model].append({
                                    'model': model,
                                    'object_id': obj.pk,
                                    'field_name': field.name,
                                    'related_model': related_model,
                                    'related_id': field_value
                                })

        # Second pass: Restore circular foreign keys
        if circular_deps:
            self.stdout.write(self.style.NOTICE("Restoring circular foreign keys..."))
            
            for model, fk_data in circular_deps.items():
                self.stdout.write(self.style.NOTICE(f"Restoring circular foreign keys for {model.__name__}"))
                
                # Get all objects from target DB for updating
                if self.uses_organization_mixin(model):
                    target_objects = list(model.unfiltered_objects.using(target_db).all())
                else:
                    target_objects = list(model.objects.using(target_db).all())
                
                # Create a mapping of PKs to objects
                target_obj_map = {obj.pk: obj for obj in target_objects}
                
                # Update each object with its original foreign key values
                for obj_id, field_values in fk_data.items():
                    if obj_id in target_obj_map:
                        target_obj = target_obj_map[obj_id]
                        for field_name, related_id in field_values.items():
                            # Set the foreign key directly using the ID field
                            setattr(target_obj, f"{field_name}_id", related_id)
                
                # Save the updated objects in batches
                for i in range(0, len(target_objects), batch_size):
                    batch = target_objects[i:i + batch_size]
                    def update_batch():
                        with transaction.atomic(using=target_db):
                            for obj in batch:
                                obj.save(using=target_db)
                    try:
                        self.retry_operation(update_batch, max_retries, retry_delay)
                    except Exception as e:
                        self.stderr.write(self.style.WARNING(
                            f"Error restoring circular foreign keys for {model.__name__}: {str(e)}"
                        ))

        # Third pass: Restore M2M relationships
        self.stdout.write(self.style.NOTICE("Restoring many-to-many relationships..."))
        
        # Process through models specially - need to ensure they exist before regular M2M restoration
        processed_through_models = set()
        
        for model, relationships in m2m_data.items():
            for obj_id, fields in relationships.items():
                try:
                    # Use appropriate manager to find object
                    if self.uses_organization_mixin(model):
                        obj = model.unfiltered_objects.using(target_db).get(pk=obj_id)
                    else:
                        obj = model.objects.using(target_db).get(pk=obj_id)
                        
                    for field_name, field_data in fields.items():
                        m2m_field = getattr(obj, field_name)
                        m2m_field.clear()
                        
                        # Check if this is a M2M with through model that needs special handling
                        has_through_data = isinstance(field_data, dict) and 'through_data' in field_data
                        
                        if has_through_data:
                            # Get the ids and through data
                            related_ids = field_data['ids']
                            through_model_name = field_data['through_model']
                            through_data = field_data['through_data']
                            
                            # Get the M2M field to access its properties
                            m2m_field_obj = model._meta.get_field(field_name)
                            through_model = m2m_field_obj.through
                            
                            # Mark this through model as processed
                            processed_through_models.add(through_model)
                            
                            self.stdout.write(self.style.NOTICE(
                                f"Restoring M2M with through model: {model.__name__}.{field_name} -> {through_model_name} "
                                f"({len(through_data)} relationships)"
                            ))
                            
                            # For through models, we need to create the through model instances directly
                            # First ensure any existing through model instances are cleared
                            through_model.objects.using(target_db).filter(**{
                                m2m_field_obj.m2m_field_name(): obj
                            }).delete()
                            
                            # Batch create the through instances
                            through_instances = []
                            
                            for rel_data in through_data:
                                related_id = rel_data['related_id']
                                extra_fields = rel_data['through_data']
                                
                                # Create the through model instance with the right fields
                                through_instance = through_model(
                                    **{
                                        m2m_field_obj.m2m_field_name(): obj,
                                        m2m_field_obj.m2m_reverse_field_name() + '_id': related_id,
                                        **extra_fields
                                    }
                                )
                                through_instances.append(through_instance)
                            
                            # Save all through instances in a batch
                            if through_instances:
                                def save_through_batch():
                                    with transaction.atomic(using=target_db):
                                        through_model.objects.using(target_db).bulk_create(
                                            through_instances, 
                                            batch_size=batch_size,
                                            ignore_conflicts=True
                                        )
                                try:
                                    self.retry_operation(save_through_batch, max_retries, retry_delay)
                                    self.stdout.write(self.style.SUCCESS(
                                        f"Saved {len(through_instances)} {through_model.__name__} instances"
                                    ))
                                except Exception as e:
                                    self.stderr.write(self.style.ERROR(
                                        f"Error saving through model instances: {str(e)}"
                                    ))
                        else:
                            # Regular M2M relationship (no through model or legacy format)
                            related_ids = field_data['ids'] if isinstance(field_data, dict) else field_data
                            
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
        
        # Fourth pass: Verify all M2M relationships including those with through models
        self.stdout.write(self.style.NOTICE("Verifying all M2M relationships..."))
        
        # Get all models with M2M relationships
        m2m_models = []
        for model in all_models:
            if any(f.many_to_many and not f.auto_created for f in model._meta.get_fields()):
                m2m_models.append(model)
        
        for model in m2m_models:
            # Get M2M fields for this model
            m2m_fields = [f for f in model._meta.get_fields() if f.many_to_many and not f.auto_created]
            
            # Skip if no M2M fields
            if not m2m_fields:
                continue
                
            self.stdout.write(self.style.NOTICE(f"Verifying M2M relationships for {model.__name__}"))
            
            # Get all instances of this model from both source and target
            if self.uses_organization_mixin(model):
                source_objects = list(model.unfiltered_objects.using(source_db).all())
                target_objects = list(model.unfiltered_objects.using(target_db).all())
            else:
                source_objects = list(model.objects.using(source_db).all())
                target_objects = list(model.objects.using(target_db).all())
            
            # Map objects by their primary keys
            source_objects_by_pk = {obj.pk: obj for obj in source_objects}
            target_objects_by_pk = {obj.pk: obj for obj in target_objects}
            
            # Check each M2M field for each object
            for field in m2m_fields:
                field_name = field.name
                
                # Check if this is a through model relationship
                has_through_model = hasattr(field, 'through') and field.through is not None
                through_model = field.through if has_through_model else None
                
                for source_obj in source_objects:
                    # Skip if object doesn't exist in target
                    if source_obj.pk not in target_objects_by_pk:
                        self.stderr.write(self.style.WARNING(
                            f"Target {model.__name__} with pk {source_obj.pk} does not exist"
                        ))
                        continue
                    
                    target_obj = target_objects_by_pk[source_obj.pk]
                    
                    # Get related objects
                    source_related = getattr(source_obj, field_name)
                    target_related = getattr(target_obj, field_name)
                    
                    # Get related IDs
                    source_related_ids = set(source_related.values_list('pk', flat=True))
                    target_related_ids = set(target_related.values_list('pk', flat=True))
                    
                    # Check if there's a mismatch
                    if source_related_ids != target_related_ids:
                        self.stdout.write(self.style.WARNING(
                            f"{model.__name__} {source_obj.pk} has mismatched {field_name}. "
                            f"Source: {sorted(source_related_ids)}, Target: {sorted(target_related_ids)}. Fixing..."
                        ))
                        
                        # Fix the relationship
                        if has_through_model:
                            # For through models, we need to recreate the through instances
                            # First, clear existing relationships
                            through_model.objects.using(target_db).filter(**{
                                field.m2m_field_name(): target_obj
                            }).delete()
                            
                            # Get through instances from source
                            source_through_objects = through_model.objects.using(source_db).filter(**{
                                field.m2m_field_name(): source_obj
                            })
                            
                            # Create new through instances in target
                            for source_through in source_through_objects:
                                # Get the related object id
                                related_id = getattr(source_through, field.m2m_reverse_field_name() + '_id')
                                
                                # Get all other fields (excluding id and the foreign keys to the main models)
                                extra_fields = {}
                                for through_field in through_model._meta.fields:
                                    field_name = through_field.name
                                    if field_name not in ('id', field.m2m_field_name(), field.m2m_reverse_field_name()):
                                        extra_fields[field_name] = getattr(source_through, field_name)
                                
                                # Create the through instance
                                try:
                                    through_model.objects.using(target_db).create(
                                        **{
                                            field.m2m_field_name(): target_obj,
                                            field.m2m_reverse_field_name() + '_id': related_id,
                                            **extra_fields
                                        }
                                    )
                                except Exception as e:
                                    self.stderr.write(self.style.ERROR(
                                        f"Error creating through model instance: {str(e)}"
                                    ))
                        else:
                            # For regular M2M fields, we can just clear and add
                            target_related.clear()
                            if source_related_ids:
                                target_related.add(*source_related_ids)
        
        # Third pass: Restore cross-model circular dependencies
        if cross_model_circular_deps:
            self.stdout.write(self.style.NOTICE("Restoring cross-model circular dependencies..."))
            
            # Group updates by model for efficiency
            updates_by_model = defaultdict(list)
            for model, updates in cross_model_circular_deps.items():
                for update in updates:
                    updates_by_model[update['model']].append(update)
            
            # Process each model's updates
            for model, updates in updates_by_model.items():
                try:
                    # Get all objects that need updating
                    object_ids = [update['object_id'] for update in updates]
                    
                    self.stdout.write(self.style.NOTICE(
                        f"Processing {len(updates)} cross-model circular dependencies for {model.__name__}"
                    ))
                    
                    # Use appropriate manager
                    if self.uses_organization_mixin(model):
                        objects = list(model.unfiltered_objects.using(target_db).filter(pk__in=object_ids))
                    else:
                        objects = list(model.objects.using(target_db).filter(pk__in=object_ids))
                    
                    self.stdout.write(self.style.NOTICE(
                        f"Found {len(objects)} of {len(object_ids)} objects in target database"
                    ))
                    
                    # Create a mapping of PKs to objects
                    obj_map = {obj.pk: obj for obj in objects}
                    
                    # Apply updates
                    updated_objects = []
                    for update in updates:
                        obj_id = update['object_id']
                        if obj_id in obj_map:
                            obj = obj_map[obj_id]
                            field_name = update['field_name']
                            related_id = update['related_id']
                            related_model = update['related_model']
                            
                            # self.stdout.write(self.style.NOTICE(
                            #     f"Updating {model.__name__} {obj_id} {field_name} -> {related_model.__name__} {related_id}"
                            # ))
                            
                            # Check if the related object exists
                            try:
                                if self.uses_organization_mixin(related_model):
                                    related_exists = related_model.unfiltered_objects.using(target_db).filter(pk=related_id).exists()
                                else:
                                    related_exists = related_model.objects.using(target_db).filter(pk=related_id).exists()
                                    
                                if related_exists:
                                    # Set the foreign key directly using the ID field
                                    setattr(obj, f"{field_name}_id", related_id)
                                    updated_objects.append(obj)
                                else:
                                    self.stdout.write(self.style.WARNING(
                                        f"Skipping update for {model.__name__} {obj_id}: "
                                        f"Related {related_model.__name__} with ID {related_id} does not exist"
                                    ))
                            except Exception as e:
                                self.stderr.write(self.style.WARNING(
                                    f"Error checking related object existence: {str(e)}"
                                ))
                        else:
                            self.stdout.write(self.style.WARNING(
                                f"Object {model.__name__} with ID {obj_id} not found in target database"
                            ))
                    
                    # Save objects in batches
                    if updated_objects:
                        self.stdout.write(self.style.NOTICE(
                            f"Saving {len(updated_objects)} updated objects"
                        ))
                        for i in range(0, len(updated_objects), batch_size):
                            batch = updated_objects[i:i + batch_size]
                            def update_batch():
                                with transaction.atomic(using=target_db):
                                    for obj in batch:
                                        obj.save(using=target_db)
                            try:
                                self.retry_operation(update_batch, max_retries, retry_delay)
                            except Exception as e:
                                self.stderr.write(self.style.ERROR(
                                    f"Error updating cross-model circular dependencies for {model.__name__}: {str(e)}"
                                ))
                    else:
                        self.stdout.write(self.style.NOTICE(
                            f"No objects to update for {model.__name__}"
                        ))
                
                except Exception as e:
                    self.stderr.write(self.style.ERROR(
                        f"Error processing cross-model circular dependencies for {model.__name__}: {str(e)}"
                    ))

        self.stdout.write(self.style.SUCCESS('Successfully completed database copy operation'))

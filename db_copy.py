#!/usr/bin/env python
import os
import django
from django.db import connections, transaction, IntegrityError
from django.apps import apps

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

def should_skip_model(model):
    if not model._meta.managed or model._meta.abstract:
        return True
    if model._meta.db_table.startswith('auth_') and model._meta.app_label != 'auth':
        return True
    return False

def get_all_db_models():
    seen = set()
    models = []
    for app_config in apps.get_app_configs():
        for model in app_config.get_models():
            if not should_skip_model(model) and model not in seen:
                seen.add(model)
                models.append(model)
    return models

def copy_model_data(model, source_db='default', target_db='staging', max_retries=5):
    model_name = f"{model._meta.app_label}.{model._meta.model_name}"
    print(f"Copying {model_name}...")
    for retry in range(1, max_retries + 1):
        try:
            source_count = model.objects.using(source_db).count()
            if source_count == 0:
                print(f"{model_name}: No data")
                return True

            with transaction.atomic(using=target_db):
                model.objects.using(target_db).all().delete()

                for obj in model.objects.using(source_db).all().iterator():
                    obj.pk = None
                    obj.save(using=target_db)

            target_count = model.objects.using(target_db).count()
            print(f"{model_name}: Done ({target_count}/{source_count})")
            return True
        except IntegrityError as e:
            if retry == max_retries:
                print(f"ERROR: {model_name} failed after {max_retries} retries due to FK constraint: {e}")
                return False
            print(f"WARNING: Retry {retry}/{max_retries}: FK violation in {model_name}. Retrying...")
        except Exception as e:
            print(f"ERROR: {model_name} failed: {e}")
            return False

def copy_database():
    print("Starting migration from default to staging")
    print("Applying migrations to staging database...")
    with connections['staging'].cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL DEFERRED")
    os.system("python manage.py migrate --database=staging")

    models = get_all_db_models()
    # Attempt to copy all models in a single pass, handling errors iteratively.
    all_copied = True
    for model in models:
        if not copy_model_data(model):
            all_copied = False

    with connections['staging'].cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    print("\nVerification:")
    for model in models:
        source_count = model.objects.using('default').count()
        target_count = model.objects.using('staging').count()
        status = "✓" if target_count >= source_count else "✗"
        print(f"{status} {model._meta.app_label}.{model._meta.model_name}: {target_count}/{source_count}")

    if all_copied:
        print("\nMigration completed successfully!")
    else:
        print("\nMigration completed with issues. Review the output for details.")

if __name__ == "__main__":
    copy_database()

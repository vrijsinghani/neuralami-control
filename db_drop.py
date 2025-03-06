#!/usr/bin/env python
import os
import django
from django.db import connections, transaction, IntegrityError
from django.apps import apps
import sys

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

def drop_all_tables(target_db='staging'):
    """
    Drop all tables in the target database.
    This ensures a clean slate for migrations and data copying.
    Uses standard database permissions without requiring superuser.
    """
    print(f"Dropping all tables in {target_db} database...")
    
    # Get a list of all tables in the database
    with connections[target_db].cursor() as cursor:
        # Get all table names
        cursor.execute("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public'
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        if not tables:
            print("No tables found to drop.")
            return
        
        print(f"Found {len(tables)} tables to drop.")
        
        # First, disable all constraints to avoid dependency issues
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        
        # Drop all tables individually
        for table in tables:
            print(f"Dropping table {table}...")
            try:
                # First try to truncate the table to remove data
                try:
                    cursor.execute(f'TRUNCATE TABLE "{table}" CASCADE')
                except Exception as e:
                    print(f"Could not truncate {table}: {e}")
                
                # Then drop the table
                cursor.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
                print(f"Table {table} dropped successfully.")
            except Exception as e:
                print(f"Error dropping table {table}: {e}")
        
        print("Completed table drop operations.")

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

def reset_staging_db():
    """
    Reset the staging database by dropping and recreating it.
    This is the most reliable way to ensure a clean slate without superuser privileges.
    """
    print("Resetting staging database...")
    
    # Get database connection parameters from Django settings
    from django.conf import settings
    db_settings = settings.DATABASES['staging']
    db_name = db_settings['NAME']
    
    # Create SQL commands to drop and recreate the database
    drop_db_sql = f"DROP DATABASE IF EXISTS {db_name};"
    create_db_sql = f"CREATE DATABASE {db_name};"
    
    # Use psycopg2 directly to connect to postgres database
    import psycopg2
    try:
        # Connect to default postgres database to execute drop/create commands
        conn = psycopg2.connect(
            dbname='postgres',
            user=db_settings['USER'],
            password=db_settings['PASSWORD'],
            host=db_settings['HOST'],
            port=db_settings['PORT']
        )
        conn.autocommit = True
        with conn.cursor() as cursor:
            print(f"Dropping database {db_name}...")
            cursor.execute(drop_db_sql)
            print(f"Creating database {db_name}...")
            cursor.execute(create_db_sql)
        conn.close()
        print(f"Database {db_name} has been reset successfully.")
        return True
    except Exception as e:
        print(f"Error resetting database: {e}")
        return False

def copy_database():
    print("Starting migration from default to staging")
    
    # Try to reset the staging database completely
    try:
        if reset_staging_db():
            print("Staging database has been reset. Applying migrations...")
        else:
            # If reset fails, try to drop tables individually
            print("Database reset failed. Attempting to drop tables individually...")
            drop_all_tables(target_db='staging')
    except Exception as e:
        print(f"Error during database reset: {e}")
        print("Attempting to drop tables individually...")
        drop_all_tables(target_db='staging')
    
    print("Applying migrations to staging database...")
    with connections['staging'].cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL DEFERRED")
    os.system("python manage.py migrate --database=staging")


if __name__ == "__main__":
    copy_database()

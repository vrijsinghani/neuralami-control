#!/usr/bin/env python
import os
import subprocess
import tempfile
import django
import sys
import glob
from django.db import connections

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

# Directory for SQL dumps
DUMP_DIR = 'sql_dumps'

def get_db_params(db_alias='staging'):
    """Get database connection parameters"""
    from django.conf import settings
    db_settings = settings.DATABASES[db_alias]
    return {
        'name': db_settings['NAME'],
        'user': db_settings['USER'],
        'password': db_settings['PASSWORD'],
        'host': db_settings['HOST'],
        'port': db_settings['PORT'],
    }

def run_psql_command(sql, db_alias='staging'):
    """Run a SQL command using psql"""
    db_params = get_db_params(db_alias)
    
    # Create temp password file
    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp:
        pgpass_line = f"{db_params['host']}:{db_params['port']}:{db_params['name']}:{db_params['user']}:{db_params['password']}"
        temp.write(pgpass_line)
        pgpass_file = temp.name
    
    try:
        # Set file permissions
        os.chmod(pgpass_file, 0o600)
        
        # Create a temp SQL file
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.sql', delete=False) as sql_file:
            sql_file.write(sql)
            sql_path = sql_file.name
        
        # Set environment variable for password
        env = os.environ.copy()
        env['PGPASSFILE'] = pgpass_file
        
        # Execute psql command
        cmd = [
            'psql',
            '--host', db_params['host'],
            '--port', db_params['port'],
            '--username', db_params['user'],
            '--dbname', db_params['name'],
            '--file', sql_path
        ]
        
        process = subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if process.returncode != 0:
            print(f"Error executing SQL: {process.stderr}")
            return False
        
        return True
        
    except Exception as e:
        print(f"Error running psql command: {e}")
        return False
    
    finally:
        # Clean up temp files
        os.unlink(pgpass_file)
        if 'sql_path' in locals():
            os.unlink(sql_path)

def drop_all_tables():
    """Drop all tables using CASCADE"""
    sql = """
    DO $$ 
    DECLARE
        r RECORD;
    BEGIN
        -- Disable triggers
        EXECUTE 'SET session_replication_role = replica;';
        
        -- Drop all tables in a single transaction with CASCADE
        FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
            EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE;';
        END LOOP;
        
        -- Re-enable triggers
        EXECUTE 'SET session_replication_role = DEFAULT;';
    END $$;
    """
    
    print("Dropping all tables in the database...")
    if run_psql_command(sql):
        print("All tables dropped successfully.")
        return True
    else:
        print("Failed to drop tables.")
        return False

def import_full_database(db_dump_path):
    """Import a full database dump"""
    db_params = get_db_params('staging')
    
    # Create temp password file
    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp:
        pgpass_line = f"{db_params['host']}:{db_params['port']}:{db_params['name']}:{db_params['user']}:{db_params['password']}"
        temp.write(pgpass_line)
        pgpass_file = temp.name
    
    try:
        # Set file permissions
        os.chmod(pgpass_file, 0o600)
        
        # Set environment variable for password
        env = os.environ.copy()
        env['PGPASSFILE'] = pgpass_file
        
        print(f"Importing database from {db_dump_path}...")
        
        # Execute psql to import the database
        cmd = [
            'psql',
            '--host', db_params['host'],
            '--port', db_params['port'],
            '--username', db_params['user'],
            '--dbname', db_params['name'],
            '-f', db_dump_path
        ]
        
        process = subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if process.returncode != 0:
            print(f"Error importing database: {process.stderr}")
            return False
        
        print("Database imported successfully.")
        return True
        
    except Exception as e:
        print(f"Error importing database: {e}")
        return False
    
    finally:
        # Clean up temp files
        os.unlink(pgpass_file)

def dump_full_database():
    """Create a complete database dump from the default database"""
    db_params = get_db_params('default')
    
    # Create temp password file
    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp:
        pgpass_line = f"{db_params['host']}:{db_params['port']}:{db_params['name']}:{db_params['user']}:{db_params['password']}"
        temp.write(pgpass_line)
        pgpass_file = temp.name
    
    try:
        # Set file permissions
        os.chmod(pgpass_file, 0o600)
        
        # Set environment variable for password
        env = os.environ.copy()
        env['PGPASSFILE'] = pgpass_file
        
        # Create output directory if it doesn't exist
        os.makedirs(DUMP_DIR, exist_ok=True)
        
        # Full dump filename
        schema_file = os.path.join(DUMP_DIR, 'schema.sql')
        data_file = os.path.join(DUMP_DIR, 'data.sql')
        
        print("Step 1: Dumping schema...")
        # First dump only the schema
        schema_cmd = [
            'pg_dump',
            '--host', db_params['host'],
            '--port', db_params['port'],
            '--username', db_params['user'],
            '--format', 'plain',
            '--schema-only',  # Only schema, no data
            '--clean',
            '--if-exists',
            '--no-owner',
            '--no-acl',
            db_params['name']
        ]
        
        with open(schema_file, 'w') as f:
            process = subprocess.run(
                schema_cmd,
                env=env,
                stdout=f,
                stderr=subprocess.PIPE,
                text=True
            )
        
        if process.returncode != 0:
            print(f"Error dumping schema: {process.stderr}")
            return None
            
        print("Step 2: Dumping data...")
        # Then dump only the data
        data_cmd = [
            'pg_dump',
            '--host', db_params['host'],
            '--port', db_params['port'],
            '--username', db_params['user'],
            '--format', 'plain',
            '--data-only',  # Only data, no schema
            '--no-owner',
            '--no-acl',
            db_params['name']
        ]
        
        with open(data_file, 'w') as f:
            process = subprocess.run(
                data_cmd,
                env=env,
                stdout=f,
                stderr=subprocess.PIPE,
                text=True
            )
        
        if process.returncode != 0:
            print(f"Error dumping data: {process.stderr}")
            return None
        
        print(f"Database schema dumped to {schema_file}")
        print(f"Database data dumped to {data_file}")
        return schema_file, data_file
        
    except Exception as e:
        print(f"Error dumping database: {e}")
        return None
    
    finally:
        # Clean up temp files
        os.unlink(pgpass_file)

def verify_import():
    """Verify that data was imported correctly by checking table counts"""
    from django.db import connections
    
    print("\nVerifying database import...")
    try:
        # Connect to staging database
        with connections['staging'].cursor() as cursor:
            # Get list of all tables
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            tables = [row[0] for row in cursor.fetchall()]
            
            if not tables:
                print("Error: No tables found in the database!")
                return False
                
            print(f"Found {len(tables)} tables in the staging database")
            
            # Check row counts for each table
            total_rows = 0
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                total_rows += count
                
                # Only print tables with data
                if count > 0:
                    print(f"  - {table}: {count} rows")
            
            print(f"\nTotal rows across all tables: {total_rows}")
            
            # Check if we have users (a critical table)
            cursor.execute("SELECT COUNT(*) FROM auth_user")
            user_count = cursor.fetchone()[0]
            if user_count == 0:
                print("Warning: No users found in auth_user table!")
            else:
                print(f"Found {user_count} users in auth_user table")
                
            return total_rows > 0
                
    except Exception as e:
        print(f"Error verifying import: {e}")
        return False

def fix_auth_user():
    """Create minimal auth_user data if missing"""
    from django.db import connections
    
    print("\nChecking auth_user table...")
    
    try:
        # Connect to both databases to compare
        with connections['default'].cursor() as source_cursor:
            with connections['staging'].cursor() as target_cursor:
                # Check if source database has users
                source_cursor.execute("SELECT COUNT(*) FROM auth_user")
                source_count = source_cursor.fetchone()[0]
                print(f"Source database has {source_count} users")
                
                # Check if target database has users
                target_cursor.execute("SELECT COUNT(*) FROM auth_user")
                target_count = target_cursor.fetchone()[0]
                print(f"Target database has {target_count} users")
                
                if target_count == 0 and source_count > 0:
                    print("Copying users from source to target database...")
                    
                    # Get all users from source database
                    source_cursor.execute("""
                        SELECT id, password, last_login, is_superuser, username, 
                               first_name, last_name, email, is_staff, is_active, 
                               date_joined 
                        FROM auth_user
                    """)
                    users = source_cursor.fetchall()
                    
                    # Insert users into target database
                    for user in users:
                        # Build the INSERT statement with placeholders
                        placeholders = ', '.join(['%s'] * len(user))
                        columns = "id, password, last_login, is_superuser, username, first_name, last_name, email, is_staff, is_active, date_joined"
                        
                        insert_sql = f"INSERT INTO auth_user ({columns}) VALUES ({placeholders})"
                        target_cursor.execute(insert_sql, user)
                    
                    connections['staging'].commit()
                    
                    # Verify the copy
                    target_cursor.execute("SELECT COUNT(*) FROM auth_user")
                    new_count = target_cursor.fetchone()[0]
                    print(f"Target database now has {new_count} users")
                    
                    return True
                elif target_count > 0:
                    print("Users already exist in target database")
                    return True
                else:
                    print("No users found in source database either!")
                    return False
    
    except Exception as e:
        print(f"Error fixing auth_user table: {e}")
        return False

def import_specific_table(table_name, db_alias='default', target_db='staging'):
    """Import data from a specific table"""
    from django.db import connections
    
    print(f"\nImporting data from {table_name}...")
    
    try:
        # Connect to both databases
        with connections[db_alias].cursor() as source_cursor:
            with connections[target_db].cursor() as target_cursor:
                # Clear target table first
                target_cursor.execute(f"DELETE FROM {table_name}")
                
                # Get column names from the table
                source_cursor.execute(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' AND table_name = %s
                """, [table_name])
                
                columns = [col[0] for col in source_cursor.fetchall()]
                columns_str = ", ".join(columns)
                
                # Get all data from source table
                source_cursor.execute(f"SELECT {columns_str} FROM {table_name}")
                rows = source_cursor.fetchall()
                
                if not rows:
                    print(f"No data found in {table_name}")
                    return False
                
                print(f"Found {len(rows)} rows to import")
                
                # Insert data into target table
                placeholders = ", ".join(["%s"] * len(columns))
                insert_sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
                
                # Insert in batches to avoid memory issues
                batch_size = 1000
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i+batch_size]
                    target_cursor.executemany(insert_sql, batch)
                
                connections[target_db].commit()
                
                # Verify import
                target_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = target_cursor.fetchone()[0]
                print(f"Imported {count} rows into {table_name}")
                
                return count > 0
    
    except Exception as e:
        print(f"Error importing {table_name}: {e}")
        return False

def main():
    """Main execution function"""
    if len(sys.argv) < 2:
        print("Usage: python db_import.py [dump|import|verify|fix-users|import-table <table_name>]")
        return
    
    action = sys.argv[1].lower()
    
    if action == 'dump':
        # Create a full database dump
        dump_full_database()
        
    elif action == 'import':
        # Find the schema and data files
        schema_file = os.path.join(DUMP_DIR, 'schema.sql')
        data_file = os.path.join(DUMP_DIR, 'data.sql')
        
        if not os.path.exists(schema_file) or not os.path.exists(data_file):
            print("Schema or data dump not found. Run 'python db_import.py dump' first.")
            return
        
        # Drop all tables in the target database
        if drop_all_tables():
            # First import schema
            print("Importing schema...")
            if import_full_database(schema_file):
                # Then import data
                print("Importing data...")
                import_full_database(data_file)
                # Fix auth_user if needed
                fix_auth_user()
                # Verify the import
                verify_import()
    
    elif action == 'verify':
        # Just run verification
        verify_import()
        
    elif action == 'fix-users':
        # Fix the auth_user table
        fix_auth_user()
        
    elif action == 'import-table':
        # Import a specific table
        if len(sys.argv) < 3:
            print("Usage: python db_import.py import-table <table_name>")
            return
            
        table_name = sys.argv[2]
        import_specific_table(table_name)
        
    else:
        print("Invalid action. Use 'dump', 'import', 'verify', 'fix-users', or 'import-table'.")

if __name__ == "__main__":
    main() 
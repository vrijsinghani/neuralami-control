#!/bin/bash
set -e

# Wait for database to be ready (optional but recommended)
if [ "$WAIT_FOR_DB" = "true" ]; then
    echo "Waiting for database to be ready..."
    python -c "
import sys
import time
import psycopg2
from os import environ

host = environ.get('DB_HOST', 'localhost')
port = environ.get('DB_PORT', '5432')
dbname = environ.get('DB_NAME', 'postgres')
user = environ.get('DB_USERNAME', 'postgres')
password = environ.get('DB_PASS', '')

for i in range(30):
    try:
        conn = psycopg2.connect(f'dbname={dbname} user={user} password={password} host={host} port={port}')
        conn.close()
        print('Database is ready!')
        break
    except psycopg2.OperationalError:
        print('Database not ready yet. Waiting...')
        time.sleep(2)
else:
    print('Could not connect to database after 30 attempts. Exiting.')
    sys.exit(1)
"
fi

# Install Uvicorn with WebSocket support
echo "Installing Uvicorn ASGI server with WebSocket support..."
pip install --no-cache-dir uvicorn[standard] websockets

# Run migrations if requested
if [ "$RUN_MIGRATIONS" = "true" ]; then
    echo "Running database migrations..."
    
    # Only run makemigrations in development environments
    if [ "$DJANGO_ENV" = "development" ]; then
        echo "Creating migrations (development only)..."
        python manage.py makemigrations
    fi
    
    echo "Applying migrations..."
    python manage.py migrate
    
    # Optionally collect static files
    if [ "$COLLECT_STATIC" = "true" ]; then
        echo "Collecting static files..."
        python manage.py collectstatic --noinput
    fi
fi

# Execute the main command
echo "Starting application..."
exec "$@" 
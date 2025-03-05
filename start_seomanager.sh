#!/bin/bash
PROJECT_DIR="$(dirname "$0")"  # Get project root directory
cd "$PROJECT_DIR"  # Change to project root directory
echo "Current directory: $(pwd)"

# Add the project directory to PYTHONPATH
export PYTHONPATH="$PROJECT_DIR:$PYTHONPATH"
export DJANGO_SETTINGS_MODULE="core.settings"

# Create directories for logs and pids if they don't exist
mkdir -p logs pids

# Ensure we're using the UV virtual environment
source .venv/bin/activate

# Start Uvicorn with nohup - using correct lifespan option
echo "Starting Uvicorn ASGI server..."
nohup uvicorn core.asgi:application --host 0.0.0.0 --port 3010 --lifespan off --ws websockets > ./logs/django.log 2>&1 &
echo $! > ./pids/django.pid

# Start Celery with nohup
echo "Starting Celery worker..."
nohup celery -A apps.tasks worker -l info -B > ./logs/celery.log 2>&1 &
echo $! > ./pids/celery.pid

echo "Services started successfully"
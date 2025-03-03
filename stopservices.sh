#!/bin/bash
echo "Stopping services..."

# Stop Django (Uvicorn) server
if [ -f ./pids/django.pid ]; then
    echo "Stopping Uvicorn server..."
    kill $(cat ./pids/django.pid) 2>/dev/null
    rm ./pids/django.pid
    echo "Uvicorn server stopped"
else
    echo "No Uvicorn PID file found"
fi

# Stop Celery worker
if [ -f ./pids/celery.pid ]; then
    echo "Stopping Celery worker..."
    kill $(cat ./pids/celery.pid) 2>/dev/null
    rm ./pids/celery.pid
    echo "Celery worker stopped"
else
    echo "No Celery PID file found"
fi

# Check for any remaining processes
if pgrep -f 'uvicorn.*core.asgi' >/dev/null; then
    echo "Forcefully stopping remaining Uvicorn processes..."
    pkill -SIGKILL -f 'uvicorn.*core.asgi'
fi

if pgrep -f 'celery -A apps.tasks' >/dev/null; then
    echo "Forcefully stopping remaining Celery processes..."
    pkill -SIGKILL -f 'celery -A apps.tasks'
fi

echo "All services stopped"
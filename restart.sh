#!/bin/bash

# Get the directory where the script is located
PROJECT_DIR="$(dirname "$0")"
cd "$PROJECT_DIR"

echo "Stopping services..."
./stopservices.sh

echo "Waiting for services to stop..."
sleep 3

# Clear Celery tasks and stop workers
echo "Stopping Celery workers and clearing tasks..."

# Try graceful shutdown first
pkill -SIGTERM -f 'celery' 2>/dev/null

sleep 3

# Handle lingering Celery processes
if pgrep -f 'celery' >/dev/null 2>&1; then
    echo "Attempting to stop remaining Celery processes..."
    pkill -SIGTERM -f 'celery' 2>/dev/null
    sleep 2
    pkill -SIGKILL -f 'celery' 2>/dev/null
fi

# Handle Daphne processes
echo "Ensuring Daphne server is stopped..."
if pgrep -f 'daphne' >/dev/null 2>&1; then
    echo "Stopping Daphne processes..."
    pkill -SIGTERM -f 'daphne' 2>/dev/null
    sleep 2
    # If processes still exist, try force kill
    if pgrep -f 'daphne' >/dev/null 2>&1; then
        echo "Force stopping remaining Daphne processes..."
        pkill -SIGKILL -f 'daphne' 2>/dev/null
    fi
fi

# Clear the queue, redirect stderr
echo "Clearing celery queue..."
celery -A core purge -f >/dev/null 2>&1

# Start services
echo "Starting services..."
./start_seomanager.sh

echo "Services have been restarted" 
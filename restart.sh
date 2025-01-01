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

# Only use sudo if processes remain, redirect stderr to prevent messy output
if pgrep -f 'celery' >/dev/null 2>&1; then
    echo "Some Celery processes require elevated permissions to stop..."
    sudo pkill -SIGTERM -f 'celery' 2>/dev/null
    sleep 2
    sudo pkill -SIGKILL -f 'celery' 2>/dev/null
fi

# Clear the queue, redirect stderr
echo "Clearing celery queue..."
celery -A core purge -f >/dev/null 2>&1

# Start services
echo "Starting services..."
./start_seomanager.sh

echo "Services have been restarted" 
#!/bin/bash

# Create the logs and pids directories if they don't exist
mkdir -p /app/logs /app/pids

# Start the Daphne server using the environment variable with fallback
nohup poetry run daphne -v 0 -u /tmp/daphne.sock core.asgi:application --bind 0.0.0.0 --port ${APP_PORT:-3010} > /app/logs/django.log 2>&1 &
echo $! > /app/pids/django.pid

echo "Daphne server is running with PID $(cat /app/pids/django.pid) on port ${DAPHNE_PORT:-3010}"

#!/bin/bash

# Create the logs and pids directories if they don't exist
mkdir -p /app/logs /app/pids

# Start the Daphne server
nohup poetry run daphne -v 0 -u /tmp/daphne.sock core.asgi:application --bind 0.0.0.0 --port 3010 > /app/logs/django.log 2>&1 &
echo $! > /app/pids/django.pid

echo "Daphne server is running with PID $(cat /app/pids/django.pid)"

#!/bin/bash
set -e

# Wait for a moment to ensure other services are ready
sleep 5

# Start Daphne with proper flags
exec daphne -b 0.0.0.0 -p ${APP_PORT:-3010} core.asgi:application

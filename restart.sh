#!/bin/bash

# Get the directory where the script is located
PROJECT_DIR="$(dirname "$0")"
cd "$PROJECT_DIR"

echo "Stopping services..."
./stopservices.sh

# Wait for 5 seconds to ensure services are properly stopped
echo "Waiting for services to stop..."
sleep 3

echo "Starting services..."
./start_seomanager.sh

echo "Services have been restarted" 
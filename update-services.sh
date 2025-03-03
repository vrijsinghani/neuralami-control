#!/bin/bash
set -e

echo "Pulling latest images..."
docker-compose pull

echo "Updating services..."
docker-compose up -d

echo "Verifying update..."
docker-compose ps

echo "Cleaning up old images..."
docker image prune -f

echo "Update completed successfully!"
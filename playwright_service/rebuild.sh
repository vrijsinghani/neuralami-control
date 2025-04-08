#!/bin/bash
# Script to rebuild and restart the Playwright service

echo "Stopping existing containers..."
docker-compose down

echo "Building new image..."
docker-compose build

echo "Starting service..."
docker-compose up -d

echo "Waiting for service to start..."
sleep 5

echo "Checking service health..."
curl -s http://localhost:${PORT:-8000}/health

echo "Testing a simple scrape..."
curl -s -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${API_KEY:-your_api_key_here}" \
  -d '{"url": "https://example.com", "formats": ["text"]}' \
  http://localhost:${PORT:-8000}/api/scrape | head -c 100

echo -e "\n\nService rebuilt and restarted!"
echo "Check logs with: docker-compose logs -f"

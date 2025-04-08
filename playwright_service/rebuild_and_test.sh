#!/bin/bash
# Script to rebuild and test the Playwright service

echo "Stopping existing containers..."
docker-compose down

echo "Building new image..."
docker-compose build

echo "Starting service..."
docker-compose up -d

echo "Waiting for service to start..."
sleep 10

echo "Testing health endpoint..."
curl -s http://localhost:${PORT:-8000}/health

echo -e "\n\nTesting metadata extraction (debug endpoint)..."
curl -s "http://localhost:${PORT:-8000}/debug/metadata?url=https://neuralami.com" \
  -H "Authorization: Bearer ${API_KEY:-your_api_key_here}" | jq .

echo -e "\n\nTesting metadata extraction (scrape endpoint)..."
curl -s -X POST "http://localhost:${PORT:-8000}/api/scrape" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${API_KEY:-your_api_key_here}" \
  -d '{"url": "https://neuralami.com", "formats": ["metadata"]}' | jq .

echo -e "\n\nService rebuilt and tested!"
echo "Check logs with: docker-compose logs -f"

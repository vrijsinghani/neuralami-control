#!/bin/bash
# Script to test metadata extraction

# Configuration
API_URL=${API_URL:-"http://localhost:8000"}
API_KEY=${API_KEY:-"your_api_key_here"}
TEST_URL=${TEST_URL:-"https://neuralami.com"}

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Testing metadata extraction for URL: $TEST_URL${NC}"
echo "API URL: $API_URL"
echo "API Key: ${API_KEY:0:4}...${API_KEY: -4}"
echo ""

# Test the debug endpoint
echo -e "${YELLOW}Testing debug endpoint...${NC}"
curl -s "$API_URL/debug/metadata?url=$TEST_URL" \
  -H "Authorization: Bearer $API_KEY" | jq .

echo ""
echo -e "${YELLOW}Testing scrape endpoint...${NC}"
curl -s -X POST "$API_URL/api/scrape" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d "{\"url\": \"$TEST_URL\", \"formats\": [\"metadata\"]}" | jq .

echo ""
echo -e "${GREEN}Tests completed!${NC}"

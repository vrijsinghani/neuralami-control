#!/bin/bash
# Script to build and deploy the Playwright API service

# Configuration
REGISTRY_URL=${REGISTRY_URL:-"registry.rijsinghani.us"}
IMAGE_NAME=${IMAGE_NAME:-"playwright-api"}
IMAGE_TAG=${IMAGE_TAG:-"latest"}
API_KEY=${API_KEY:-"neuralamiPlaywright1"}
PORT=${PORT:-8000}

# Full image name
FULL_IMAGE_NAME="$REGISTRY_URL/$IMAGE_NAME:$IMAGE_TAG"

# Build the Docker image
echo "Building Docker image: $FULL_IMAGE_NAME"
docker build -t "$FULL_IMAGE_NAME" .

# Push to registry
echo "Pushing image to registry: $FULL_IMAGE_NAME"
docker push "$FULL_IMAGE_NAME"

echo "Image built and pushed successfully!"

# Instructions for Portainer deployment
echo ""
echo "To deploy in Portainer Swarm:"
echo "1. Go to your Portainer instance"
echo "2. Navigate to Stacks"
echo "3. Create a new stack"
echo "4. Use the portainer-stack.yml file as a template"
echo "5. Set the environment variables:"
echo "   - REGISTRY_URL: $REGISTRY_URL"
echo "   - API_KEY: [your secure API key]"
echo "   - PORT: $PORT (optional, default is 8000)"
echo ""
echo "Done!"

#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

# Configuration
REGISTRY="registry.rijsinghani.us"
PROJECT="neuralami"
ENVIRONMENT="staging"  # Can be changed to "production" or other environments
VERSION=$(git describe --tags --always --dirty || echo "latest")

echo "Building Docker images for $PROJECT ($ENVIRONMENT) version: $VERSION"

# Build the main application image
echo "Building main application image..."
docker build \
  --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
  --build-arg VERSION=$VERSION \
  -t $REGISTRY/$PROJECT:$ENVIRONMENT \
  -t $REGISTRY/$PROJECT:$VERSION \
  -t $REGISTRY/$PROJECT:latest \
  .

# Build the worker image
echo "Building worker image..."
docker build \
  --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
  --build-arg VERSION=$VERSION \
  -t $REGISTRY/$PROJECT-worker:$ENVIRONMENT \
  -t $REGISTRY/$PROJECT-worker:$VERSION \
  -t $REGISTRY/$PROJECT-worker:latest \
  -f worker/Dockerfile \
  .

# Push images to registry
echo "Pushing images to registry..."
docker push $REGISTRY/$PROJECT:$ENVIRONMENT
docker push $REGISTRY/$PROJECT:$VERSION
docker push $REGISTRY/$PROJECT:latest
docker push $REGISTRY/$PROJECT-worker:$ENVIRONMENT
docker push $REGISTRY/$PROJECT-worker:$VERSION
docker push $REGISTRY/$PROJECT-worker:latest

echo "Docker build and push completed successfully!"
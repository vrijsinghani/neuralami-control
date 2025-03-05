#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

# Configuration
REGISTRY="registry.rijsinghani.us"
PROJECT="neuralami"
VERSION=$(git describe --tags --always --dirty || echo "latest")
COMMIT=$(git rev-parse --short HEAD || echo "unknown")
COMMIT_DATE=$(git show -s --format=%ct HEAD || echo $(date +%s))

echo "Building Docker images for $PROJECT version: $VERSION (commit: $COMMIT, date: $COMMIT_DATE)"

# Ensure requirements.txt is up to date
echo "Updating requirements.txt..."
uv pip freeze > requirements.txt

# Build the main application image
echo "Building main application image..."
docker build \
    --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
    --build-arg VERSION="$VERSION" \
    --build-arg COMMIT="$COMMIT" \
    --build-arg COMMIT_DATE="$COMMIT_DATE" \
    -t "$REGISTRY/$PROJECT:$VERSION" \
    -t "$REGISTRY/$PROJECT:latest" \
    .

# Build the worker image (used for both celery_worker and celery_beat)
echo "Building worker image..."
docker build \
    --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
    --build-arg VERSION="$VERSION" \
    --build-arg COMMIT="$COMMIT" \
    --build-arg COMMIT_DATE="$COMMIT_DATE" \
    -t "$REGISTRY/$PROJECT-worker:$VERSION" \
    -t "$REGISTRY/$PROJECT-worker:latest" \
    -f worker/Dockerfile \
    .

# Note: Redis uses the official Redis image, so we don't need to build it

# Push images to registry
echo "Pushing images to registry..."
docker push "$REGISTRY/$PROJECT:$VERSION"
docker push "$REGISTRY/$PROJECT:latest"
docker push "$REGISTRY/$PROJECT-worker:$VERSION"
docker push "$REGISTRY/$PROJECT-worker:latest"

echo "Docker build and push completed successfully!"
#!/bin/bash
set -e

# Print environment for debugging
echo "Starting Playwright API service on port $PORT"

# Install Playwright browsers
echo "Installing/updating Playwright browsers..."
playwright install --with-deps chromium
# Force reinstall if needed
if [ ! -f "/ms-playwright/chromium-1084/chrome-linux/chrome" ]; then
  echo "Forcing browser reinstallation..."
  PLAYWRIGHT_BROWSERS_PATH=/ms-playwright playwright install --with-deps chromium
fi

# Start the FastAPI application with uvicorn
exec uvicorn app:app --host 0.0.0.0 --port $PORT

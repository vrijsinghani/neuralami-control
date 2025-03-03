#!/bin/bash

# Start Uvicorn with the specified settings - using correct lifespan option
exec uvicorn core.asgi:application --host 0.0.0.0 --port ${APP_PORT:-3010} --lifespan off --ws websockets 
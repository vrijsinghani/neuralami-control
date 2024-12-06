#!/bin/bash
nohup poetry run daphne -u /tmp/daphne.sock core.asgi:application --bind 0.0.0.0 --port 3010 > ./logs/django.log 2>&1 &
echo $! > ./pids/django.pid
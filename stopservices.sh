#!/bin/bash
if [ -f ./pids/django.pid ]; then
    kill $(cat ./pids/django.pid)
    rm ./pids/django.pid
fi

if [ -f ./pids/celery.pid ]; then
    kill $(cat ./pids/celery.pid)
    rm ./pids/celery.pid
fi
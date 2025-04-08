#!/usr/bin/env python
"""
Test script for the stop button functionality.
Run with: python manage.py shell < test_stop_button.py
"""
import sys
import logging
import time
from celery.contrib.abortable import AbortableAsyncResult
from apps.crawl_website.tasks import crawl_website_task

# Set up logging to see debug messages
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Start a crawl task
task_id = "test_task_id_" + str(int(time.time()))
print(f"Starting crawl task with ID: {task_id}")

task = crawl_website_task.apply_async(
    kwargs={
        "task_id": task_id,
        "website_url": "https://www.paradisefloorsandmore.com/",
        "user_id": 1,
        "max_pages": 20,
        "max_depth": 2,
        "output_format": "text",
        "mode": "sitemap"
    },
    task_id=task_id
)

# Wait for the task to start
print("Waiting for task to start...")
time.sleep(5)

# Check task status
result = AbortableAsyncResult(task_id)
print(f"Task status before cancellation: {result.state}")

# Cancel the task
print("Cancelling task...")
result.revoke(terminate=True)
print("Task revoked")

# Wait for the task to be cancelled
print("Waiting for task to be cancelled...")
time.sleep(5)

# Check task status again
result = AbortableAsyncResult(task_id)
print(f"Task status after cancellation: {result.state}")

# Wait a bit more to see if the task is really cancelled
print("Waiting a bit more...")
time.sleep(5)

# Check task status one more time
result = AbortableAsyncResult(task_id)
print(f"Final task status: {result.state}")

print("Test completed")

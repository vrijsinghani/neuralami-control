#!/usr/bin/env python
"""
Test script for the web crawler fixes.
Run with: python manage.py shell < test_crawler_fixes.py
"""
import sys
import logging
import json
import time
import re
from apps.agents.tools.web_crawler_tool.web_crawler_tool import crawl_website, CrawlMode
from celery.result import AsyncResult
from apps.crawl_website.tasks import crawl_website_task
from celery import current_app

# Set up logging to see debug messages
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def progress_callback(current, total, url):
    """Progress callback function."""
    print(f"Progress: {current}/{total} - {url}")

def test_include_patterns():
    """Test the include patterns functionality."""
    print("\n\n=== Testing include patterns with URL: https://htmx.org/ ===\n")

    # Test with include patterns
    include_patterns = [r".*examples.*", r".*docs.*"]
    print(f"Using include patterns: {include_patterns}")

    result = crawl_website(
        start_url="https://htmx.org/",
        max_pages=10,
        max_depth=1,
        output_format=["text"],
        delay_seconds=1.0,
        mode="sitemap",
        include_patterns=include_patterns,
        progress_callback=progress_callback
    )

    print(f"Crawl mode used: {result.get('crawl_mode', 'unknown')}")
    print(f"Elapsed time: {result.get('elapsed_time', 0):.2f} seconds")
    print(f"Stats: {result.get('stats', {})}")

    if "results" in result and result["results"]:
        print(f"Number of results: {len(result['results'])}")
        print("URLs crawled:")
        for item in result["results"]:
            print(f"  - {item.get('url', 'No URL')}")
    else:
        print("No results found")

    return result

def test_stop_button():
    """Test the stop button functionality."""
    print("\n\n=== Testing stop button functionality with URL: https://htmx.org/ ===\n")

    # Start a crawl task
    task_id = f"test_task_id_{int(time.time())}"
    task = crawl_website_task.apply_async(
        kwargs={
            "task_id": task_id,
            "website_url": "https://htmx.org/",
            "user_id": 1,
            "max_pages": 20,
            "max_depth": 2,
            "output_format": ["text"],
            "delay_seconds": 5.0,
            "mode": "sitemap"
        },
        task_id=task_id
    )

    print(f"Started crawl task with ID: {task_id}")

    # Wait for the task to start
    time.sleep(5)

    # Check task status
    result = AsyncResult(task_id)
    print(f"Task status before cancellation: {result.status}")

    # Cancel the task
    print("Cancelling task...")
    current_app.control.revoke(task_id, terminate=True)
    print(f"Task {task_id} revoked with terminate=True")

    # Wait for the task to be cancelled
    time.sleep(5)

    # Check task status again
    result = AsyncResult(task_id)
    print(f"Task status after cancellation: {result.status}")

    return result

def main():
    """Run the tests."""
    print("\n=== Starting web crawler fixes tests ===\n")

    # Test include patterns
    include_patterns_result = test_include_patterns()

    # Test stop button
    stop_button_result = test_stop_button()

    print("\n=== All tests completed ===\n")

if __name__ == "__main__":
    main()
